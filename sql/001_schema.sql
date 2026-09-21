-- 001 · papers and chunks
--
-- Applied by docker-entrypoint-initdb.d on a fresh volume, and by
-- `askarxiv db init` against an existing database. Every statement is
-- idempotent so re-running is safe.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
    arxiv_id         text PRIMARY KEY,
    title            text        NOT NULL,
    abstract         text        NOT NULL,
    primary_category text        NOT NULL,
    categories       text[]      NOT NULL DEFAULT '{}',
    authors          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created          date        NOT NULL,
    updated          date,
    doi              text,
    license          text,
    ingested_at      timestamptz NOT NULL DEFAULT now(),

    -- The lexical arm of hybrid search (day 6) reads this column. It is
    -- GENERATED rather than maintained by the loader so it cannot drift from
    -- the text it indexes: there is no code path that updates title without
    -- updating the vector. Title is weighted above abstract because a term in
    -- the title is a stronger signal about what a paper is for.
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
    ) STORED
);

CREATE INDEX IF NOT EXISTS papers_search_idx   ON papers USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS papers_created_idx  ON papers (created);
CREATE INDEX IF NOT EXISTS papers_category_idx ON papers (primary_category);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    bigserial PRIMARY KEY,
    arxiv_id    text NOT NULL REFERENCES papers (arxiv_id) ON DELETE CASCADE,

    -- 'fixed512' (baseline) or 'section' (challenger). Both strategies live in
    -- the same table so a query can compare them without a schema change, and
    -- so hit rate is measured against one corpus rather than two.
    strategy    text NOT NULL,
    ordinal     int  NOT NULL,
    text        text NOT NULL,
    token_count int  NOT NULL,

    -- 384 dimensions: bge-small-en-v1.5. Changing the embedding model means
    -- changing this, which is deliberate — a mismatched dimension should fail
    -- at insert rather than produce meaningless distances.
    embedding   vector(384),

    UNIQUE (arxiv_id, strategy, ordinal)
);

CREATE INDEX IF NOT EXISTS chunks_paper_idx ON chunks (arxiv_id, strategy);
