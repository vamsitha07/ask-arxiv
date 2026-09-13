"""OAI-PMH response parsing.

Kept separate from the HTTP client so it can be tested against a fixture with
no network, which is the only way this stays honest in CI.
"""

from __future__ import annotations

from datetime import date
from xml.etree import ElementTree as ET

from askarxiv.models import Author, Paper

OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
ARXIV_NS = "{http://arxiv.org/OAI/arXiv/}"


class OaiError(RuntimeError):
    """The endpoint returned an <error> element rather than records."""


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    stripped = node.text.strip()
    return stripped or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.strip()[:10])


def parse_authors(node: ET.Element | None) -> list[Author]:
    if node is None:
        return []
    authors: list[Author] = []
    for a in node.findall(f"{ARXIV_NS}author"):
        keyname = _text(a.find(f"{ARXIV_NS}keyname"))
        if not keyname:
            continue
        authors.append(Author(keyname=keyname, forenames=_text(a.find(f"{ARXIV_NS}forenames"))))
    return authors


def parse_record(record: ET.Element) -> Paper | None:
    """Return a Paper, or None for records we deliberately skip.

    Skipped: tombstones (header status="deleted") and records whose metadata
    block is absent. Both are normal in an OAI feed and neither is an error.
    """
    header = record.find(f"{OAI_NS}header")
    if header is not None and header.get("status") == "deleted":
        return None

    meta = record.find(f"{OAI_NS}metadata/{ARXIV_NS}arXiv")
    if meta is None:
        return None

    arxiv_id = _text(meta.find(f"{ARXIV_NS}id"))
    title = _text(meta.find(f"{ARXIV_NS}title"))
    abstract = _text(meta.find(f"{ARXIV_NS}abstract"))
    created = _parse_date(_text(meta.find(f"{ARXIV_NS}created")))
    if not (arxiv_id and title and abstract and created):
        return None

    categories = (_text(meta.find(f"{ARXIV_NS}categories")) or "").split()
    if not categories:
        return None

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        categories=categories,
        # arXiv lists the primary category first.
        primary_category=categories[0],
        authors=parse_authors(meta.find(f"{ARXIV_NS}authors")),
        created=created,
        updated=_parse_date(_text(meta.find(f"{ARXIV_NS}updated"))),
        doi=_text(meta.find(f"{ARXIV_NS}doi")),
        license=_text(meta.find(f"{ARXIV_NS}license")),
    )


def parse_list_records(xml: str | bytes) -> tuple[list[Paper], str | None]:
    """Parse one ListRecords page.

    Returns the papers on the page and the resumption token, or None when the
    feed is exhausted. An empty <resumptionToken/> means the same thing as no
    token at all, which is the detail that turns a finished harvest into an
    infinite loop if you miss it.
    """
    root = ET.fromstring(xml)

    error = root.find(f"{OAI_NS}error")
    if error is not None:
        raise OaiError(f"{error.get('code')}: {(error.text or '').strip()}")

    papers: list[Paper] = []
    for record in root.iter(f"{OAI_NS}record"):
        paper = parse_record(record)
        if paper is not None:
            papers.append(paper)

    token_node = root.find(f"{OAI_NS}ListRecords/{OAI_NS}resumptionToken")
    token = _text(token_node) if token_node is not None else None
    return papers, token


def parse_complete_list_size(xml: str | bytes) -> int | None:
    """Total record count advertised on the first page, when the server sends it."""
    root = ET.fromstring(xml)
    token_node = root.find(f"{OAI_NS}ListRecords/{OAI_NS}resumptionToken")
    if token_node is None:
        return None
    raw = token_node.get("completeListSize")
    return int(raw) if raw and raw.isdigit() else None
