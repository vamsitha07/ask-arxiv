"""Postgres access: schema application and an idempotent JSONL loader.

Loading is idempotent because the harvest is resumable. Re-running a partial
harvest re-emits records already on disk, and a loader that could not absorb
that safely would make the resumability pointless.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg

from askarxiv import config
from askarxiv.models import Paper

SCHEMA_DIR = config.REPO_ROOT / "sql"

UPSERT = """
INSERT INTO papers (
    arxiv_id, title, abstract, primary_category, categories,
    authors, created, updated, doi, license
) VALUES (
    %(arxiv_id)s, %(title)s, %(abstract)s, %(primary_category)s, %(categories)s,
    %(authors)s, %(created)s, %(updated)s, %(doi)s, %(license)s
)
ON CONFLICT (arxiv_id) DO UPDATE SET
    title            = EXCLUDED.title,
    abstract         = EXCLUDED.abstract,
    primary_category = EXCLUDED.primary_category,
    categories       = EXCLUDED.categories,
    authors          = EXCLUDED.authors,
    created          = EXCLUDED.created,
    updated          = EXCLUDED.updated,
    doi              = EXCLUDED.doi,
    license          = EXCLUDED.license
RETURNING (xmax = 0) AS inserted
"""


@dataclass
class LoadResult:
    """What a load did, separated so a re-run is visibly a no-op."""

    inserted: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated


def connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or config.DbConfig().dsn)


def schema_files() -> list[Path]:
    """Migration files in lexical order — the numeric prefix is the ordering."""
    return sorted(SCHEMA_DIR.glob("*.sql"))


def apply_schema(conn: psycopg.Connection) -> list[str]:
    applied = []
    with conn.cursor() as cur:
        for path in schema_files():
            cur.execute(path.read_text())
            applied.append(path.name)
    conn.commit()
    return applied


def paper_params(paper: Paper) -> dict:
    """Flatten a Paper into bind parameters.

    Authors go in as JSON rather than a second table: nothing in this project
    queries by author, and a join that no query uses is a cost with no payer.
    """
    return {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "abstract": paper.abstract,
        "primary_category": paper.primary_category,
        "categories": list(paper.categories),
        "authors": json.dumps([a.model_dump() for a in paper.authors]),
        "created": paper.created,
        "updated": paper.updated,
        "doi": paper.doi,
        "license": paper.license,
    }


def read_jsonl(path: Path) -> Iterator[Paper]:
    """Parse the harvester's sink. Blank lines are skipped, not fatal."""
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield Paper.model_validate_json(line)


def load_papers(
    conn: psycopg.Connection, papers: Iterable[Paper], batch_size: int = 500
) -> LoadResult:
    """Upsert papers, counting inserts and updates separately."""
    result = LoadResult()
    batch: list[dict] = []

    def flush() -> None:
        if not batch:
            return
        with conn.cursor() as cur:
            for params in batch:
                cur.execute(UPSERT, params)
                row = cur.fetchone()
                # RETURNING (xmax = 0) is true only for a genuine insert, which
                # is how a re-run proves itself a no-op rather than a rewrite.
                if row and row[0]:
                    result.inserted += 1
                else:
                    result.updated += 1
        conn.commit()
        batch.clear()

    for paper in papers:
        batch.append(paper_params(paper))
        if len(batch) >= batch_size:
            flush()
    flush()
    return result


def load_jsonl(conn: psycopg.Connection, path: Path, batch_size: int = 500) -> LoadResult:
    return load_papers(conn, read_jsonl(path), batch_size=batch_size)


def count_papers(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM papers")
        row = cur.fetchone()
        return int(row[0]) if row else 0
