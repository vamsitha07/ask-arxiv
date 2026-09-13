"""Harvester behaviour, exercised against fixtures with a fake transport.

No network in these tests: the point is to prove resumption and checkpointing
work, and neither of those needs arXiv to be reachable.
"""

from datetime import date
from pathlib import Path

import pytest

from askarxiv.harvest import Harvester, HarvestState, months_ago


class FakeHarvester(Harvester):
    """Harvester with fetch() replaced by a scripted sequence of pages."""

    def __init__(self, pages: list[str]):
        super().__init__(endpoint="http://fake.invalid/oai2")
        self._pages = list(pages)
        self.requests: list[dict] = []

    def fetch(self, params):  # type: ignore[override]
        self.requests.append(dict(params))
        if not self._pages:
            raise AssertionError("harvester asked for more pages than the feed has")
        return self._pages.pop(0)


def test_harvest_follows_resumption_token_and_filters_category(tmp_path, page1, page2):
    harvester = FakeHarvester([page1, page2])
    out, state = tmp_path / "papers.jsonl", tmp_path / "harvest.json"

    papers = list(harvester.harvest(out, state, from_date=date(2026, 3, 1), category="cs.AI"))

    # cs.AR paper dropped by the category filter, tombstone dropped by the parser.
    assert [p.arxiv_id for p in papers] == ["2603.01234", "2604.00042"]
    assert len(out.read_text().strip().splitlines()) == 2

    # First request carries the query; the second carries only the token.
    assert harvester.requests[0]["from"] == "2026-03-01"
    assert harvester.requests[0]["set"] == "cs"
    assert harvester.requests[1] == {
        "verb": "ListRecords",
        "resumptionToken": "TOKEN-PAGE-2",
    }


def test_state_is_checkpointed_and_marked_finished(tmp_path, page1, page2):
    harvester = FakeHarvester([page1, page2])
    out, state = tmp_path / "papers.jsonl", tmp_path / "harvest.json"
    list(harvester.harvest(out, state, from_date=date(2026, 3, 1)))

    saved = HarvestState.load(state)
    assert saved is not None
    assert saved.finished is True
    assert saved.resumption_token is None
    assert saved.pages_fetched == 2
    assert saved.records_seen == 3  # two on page 1, one on page 2
    assert saved.records_kept == 2
    assert saved.complete_list_size == 1372


def test_a_crashed_harvest_resumes_from_its_token(tmp_path, page1, page2):
    out, state = tmp_path / "papers.jsonl", tmp_path / "harvest.json"

    # First run dies after page 1.
    first = FakeHarvester([page1])
    with pytest.raises(AssertionError):
        list(first.harvest(out, state, from_date=date(2026, 3, 1)))

    mid = HarvestState.load(state)
    assert mid is not None and mid.resumption_token == "TOKEN-PAGE-2"

    # Second run picks up where it stopped and does not refetch page 1.
    second = FakeHarvester([page2])
    resumed = list(second.harvest(out, state, from_date=date(2026, 3, 1)))

    assert [p.arxiv_id for p in resumed] == ["2604.00042"]
    assert second.requests == [{"verb": "ListRecords", "resumptionToken": "TOKEN-PAGE-2"}]
    # Appended, not truncated: both runs' records are on disk exactly once.
    assert len(out.read_text().strip().splitlines()) == 2


def test_finished_harvest_is_not_redone(tmp_path, page1, page2):
    out, state = tmp_path / "papers.jsonl", tmp_path / "harvest.json"
    list(FakeHarvester([page1, page2]).harvest(out, state, from_date=date(2026, 3, 1)))

    again = FakeHarvester([])  # any request at all would raise
    assert list(again.harvest(out, state, from_date=date(2026, 3, 1))) == []


def test_state_write_is_atomic(tmp_path):
    state_path = tmp_path / "nested" / "harvest.json"
    HarvestState(resumption_token="abc", pages_fetched=3).save(state_path)
    assert not state_path.with_suffix(".tmp").exists()
    assert HarvestState.load(state_path).resumption_token == "abc"


def test_months_ago_is_reproducible():
    assert months_ago(6, today=date(2026, 9, 13)) == date(2026, 3, 17)


def test_load_returns_none_for_a_fresh_checkout():
    assert HarvestState.load(Path("/nonexistent/harvest.json")) is None
