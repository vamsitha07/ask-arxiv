"""OAI-PMH harvester with resumption, checkpointing and polite backoff.

A harvest that dies at record 40,000 and starts over is not a harvester, so
every page is appended to disk and the resumption token is checkpointed before
the next request goes out.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import requests

from askarxiv import config
from askarxiv.models import Paper
from askarxiv.parse import parse_complete_list_size, parse_list_records


@dataclass
class HarvestState:
    """What a resumed harvest needs to know. Written after every page."""

    resumption_token: str | None = None
    pages_fetched: int = 0
    records_seen: int = 0
    records_kept: int = 0
    complete_list_size: int | None = None
    params: dict[str, str] = field(default_factory=dict)
    finished: bool = False

    @classmethod
    def load(cls, path: Path) -> HarvestState | None:
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text()))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.replace(path)  # atomic: a crash mid-write can't corrupt the checkpoint


class Harvester:
    def __init__(self, endpoint: str | None = None, session: requests.Session | None = None):
        self.endpoint = endpoint or config.OAI_ENDPOINT
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < config.MIN_REQUEST_INTERVAL:
            time.sleep(config.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def fetch(self, params: dict[str, str]) -> str:
        """One request, with 503/Retry-After honoured.

        arXiv answers a too-eager harvester with 503 and a Retry-After header
        rather than a 429. Treating it as a hard failure is how people get
        blocked; sleeping for exactly as long as asked is how you don't.
        """
        for _attempt in range(config.MAX_RETRIES):
            self._throttle()
            response = self.session.get(
                self.endpoint, params=params, timeout=config.REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response.text
            if response.status_code in (429, 503):
                wait = _retry_after_seconds(response.headers.get("Retry-After"))
                time.sleep(wait)
                continue
            response.raise_for_status()
        raise RuntimeError(f"giving up after {config.MAX_RETRIES} retries: {params}")

    def harvest(
        self,
        out_path: Path,
        state_path: Path,
        from_date: date,
        until_date: date | None = None,
        oai_set: str = "cs",
        category: str | None = "cs.AI",
        resume: bool = True,
    ) -> Iterator[Paper]:
        """Stream papers, appending JSONL and checkpointing as it goes.

        `category` filters inside the record because arXiv's OAI sets stop at
        the archive level: there is a `cs` set, there is no `cs.AI` set.
        """
        state = HarvestState.load(state_path) if resume else None
        if state and state.finished:
            return
        if state is None:
            state = HarvestState(
                params={
                    "verb": "ListRecords",
                    "metadataPrefix": "arXiv",
                    "set": oai_set,
                    "from": from_date.isoformat(),
                    **({"until": until_date.isoformat()} if until_date else {}),
                }
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if (resume and state.pages_fetched) else "w"

        with out_path.open(mode, encoding="utf-8") as sink:
            while True:
                # A resumption token is exclusive of every other argument.
                params = (
                    {"verb": "ListRecords", "resumptionToken": state.resumption_token}
                    if state.resumption_token
                    else dict(state.params)
                )
                xml = self.fetch(params)

                if state.complete_list_size is None:
                    state.complete_list_size = parse_complete_list_size(xml)

                papers, token = parse_list_records(xml)
                state.pages_fetched += 1
                state.records_seen += len(papers)

                for paper in papers:
                    if category and not paper.has_category(category):
                        continue
                    sink.write(paper.model_dump_json() + "\n")
                    state.records_kept += 1
                    yield paper

                sink.flush()
                state.resumption_token = token
                state.finished = token is None
                state.save(state_path)

                if state.finished:
                    return


def _retry_after_seconds(header: str | None) -> int:
    if header and header.strip().isdigit():
        return max(1, int(header.strip()))
    return config.DEFAULT_RETRY_AFTER


def months_ago(months: int, today: date | None = None) -> date:
    """Approximate month arithmetic, deliberately.

    The corpus boundary is a product decision, not a calendar one: six months
    means "roughly the last half year of papers", and 30-day months make the
    window reproducible from any machine without a dateutil dependency.
    """
    return (today or date.today()) - timedelta(days=30 * months)
