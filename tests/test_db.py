"""Loader behaviour, exercised without a database.

The upsert semantics are proved against a live postgres in
tests/test_db_integration.py. These tests cover the parts that are pure
Python — parameter flattening, batching, and the insert/update tally — so a
broken loader is caught on every push rather than only when docker is up.
"""

import json
from datetime import date
from pathlib import Path

from askarxiv import db
from askarxiv.models import Author, Paper


def make_paper(arxiv_id="2603.01234", **over) -> Paper:
    base = dict(
        arxiv_id=arxiv_id,
        title="Parent-Child Retrieval",
        abstract="We study section-aware chunking.",
        categories=["cs.AI", "cs.IR"],
        primary_category="cs.AI",
        authors=[Author(keyname="Okafor", forenames="Ada")],
        created=date(2026, 3, 3),
    )
    base.update(over)
    return Paper(**base)


class FakeCursor:
    """Records executed statements and answers RETURNING (xmax = 0)."""

    def __init__(self, inserted_flags):
        self.flags = list(inserted_flags)
        self.executed = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = (self.flags.pop(0),) if self.flags else (True,)

    def fetchone(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, inserted_flags=()):
        self.cursor_obj = FakeCursor(inserted_flags)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


def test_params_flatten_for_binding():
    p = db.paper_params(make_paper())
    assert p["arxiv_id"] == "2603.01234"
    assert p["categories"] == ["cs.AI", "cs.IR"]  # text[] wants a list
    assert json.loads(p["authors"])[0]["keyname"] == "Okafor"  # jsonb wants a string
    assert p["created"] == date(2026, 3, 3)
    assert p["updated"] is None


def test_every_bound_name_is_supplied():
    """Guard against the insert list and the params dict drifting apart."""
    import re

    bound = set(re.findall(r"%\((\w+)\)s", db.UPSERT))
    assert bound == set(db.paper_params(make_paper()))


def test_upsert_updates_rather_than_failing():
    assert "ON CONFLICT (arxiv_id) DO UPDATE" in db.UPSERT
    assert "RETURNING (xmax = 0)" in db.UPSERT


def test_counts_inserts_and_updates_separately():
    conn = FakeConn(inserted_flags=[True, False, True])
    result = db.load_papers(conn, [make_paper("a"), make_paper("b"), make_paper("c")])
    assert (result.inserted, result.updated, result.total) == (2, 1, 3)


def test_batches_commit_per_batch():
    conn = FakeConn(inserted_flags=[True] * 5)
    papers = [make_paper(str(i)) for i in range(5)]
    db.load_papers(conn, papers, batch_size=2)
    # 2 + 2 + 1, so three flushes — a crash costs one batch, not the run.
    assert conn.commits == 3


def test_empty_input_does_not_open_a_transaction():
    conn = FakeConn()
    result = db.load_papers(conn, [])
    assert result.total == 0
    assert conn.commits == 0


def test_read_jsonl_skips_blank_lines(tmp_path: Path):
    f = tmp_path / "papers.jsonl"
    f.write_text(
        make_paper("a").model_dump_json() + "\n\n" + make_paper("b").model_dump_json() + "\n"
    )
    assert [p.arxiv_id for p in db.read_jsonl(f)] == ["a", "b"]


def test_schema_files_apply_in_numeric_order():
    names = [p.name for p in db.schema_files()]
    assert names == sorted(names)
    assert names[0].startswith("001")


def test_schema_is_rerunnable():
    """Every statement guarded, so `db-init` on an existing database is safe."""
    sql = db.schema_files()[0].read_text().upper()
    creates = sql.count("CREATE TABLE") + sql.count("CREATE INDEX") + sql.count("CREATE EXTENSION")
    assert creates == sql.count("IF NOT EXISTS")


def test_generated_column_cannot_be_written_by_the_loader():
    """search_vector is derived; the loader must never supply it."""
    assert "search_vector" not in db.UPSERT
