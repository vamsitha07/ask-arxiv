"""Round-trip against a real postgres.

Skipped unless one is reachable, so `make test` stays green without docker.
Run it with `make itest`.
"""

from datetime import date

import pytest

from askarxiv import db
from askarxiv.models import Author, Paper

pytestmark = pytest.mark.integration


def _reachable() -> bool:
    try:
        with db.connect():
            return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _reachable(), reason="no postgres — run make db-up")


def paper(arxiv_id: str, title: str = "First title") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract="An abstract about reciprocal rank fusion.",
        categories=["cs.AI"],
        primary_category="cs.AI",
        authors=[Author(keyname="Duarte", forenames="Ines")],
        created=date(2026, 4, 1),
    )


@pytest.fixture
def conn():
    with db.connect() as c:
        db.apply_schema(c)
        with c.cursor() as cur:
            cur.execute("DELETE FROM papers WHERE arxiv_id LIKE 'test.%'")
        c.commit()
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM papers WHERE arxiv_id LIKE 'test.%'")
        c.commit()


@requires_db
def test_schema_applies_twice(conn):
    db.apply_schema(conn)  # the second application must not raise


@requires_db
def test_insert_then_reload_is_an_update_not_a_duplicate(conn):
    first = db.load_papers(conn, [paper("test.1")])
    assert (first.inserted, first.updated) == (1, 0)

    second = db.load_papers(conn, [paper("test.1", title="Corrected title")])
    assert (second.inserted, second.updated) == (0, 1)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(title) FROM papers WHERE arxiv_id = 'test.1'")
        count, title = cur.fetchone()
    assert count == 1
    assert title == "Corrected title"


@requires_db
def test_search_vector_is_generated_and_searchable(conn):
    db.load_papers(conn, [paper("test.2")])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM papers "
            "WHERE arxiv_id = 'test.2' AND search_vector @@ to_tsquery('english', 'reciprocal')"
        )
        assert cur.fetchone()[0] == 1


@requires_db
def test_chunks_cascade_when_a_paper_is_deleted(conn):
    db.load_papers(conn, [paper("test.3")])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chunks (arxiv_id, strategy, ordinal, text, token_count) "
            "VALUES ('test.3', 'fixed512', 0, 'chunk text', 3)"
        )
        conn.commit()
        cur.execute("DELETE FROM papers WHERE arxiv_id = 'test.3'")
        conn.commit()
        cur.execute("SELECT count(*) FROM chunks WHERE arxiv_id = 'test.3'")
        assert cur.fetchone()[0] == 0
