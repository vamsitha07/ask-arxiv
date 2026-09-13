# Ask arXiv

> **Live demo:** not deployed yet — link lands day 14.

Retrieval over six months of cs.AI papers that answers a real question better
than the default tutorial pipeline, with an eval harness that catches it
inventing answers and blocks the merge when it does.

Two projects, one repo, because the eval harness in the second is what measures
the retriever in the first. Splitting them would let each one grade itself.

## Problem

The default RAG tutorial chunks a document into fixed 512-token windows,
embeds them, and returns the top k by cosine similarity. It demos well. On real
scientific papers it retrieves half a method section and hands the model a
fragment with no context, and nobody notices because nobody measured it.

Two things are missing from that pipeline, and both are the actual job:

1. A **question set written by a human** that the system is scored against.
2. A **failure mode that is caught before merge**, not after a user finds it.

## Decision

| Decision | Choice | Why |
|---|---|---|
| Corpus | cs.AI metadata + abstracts, last 6 months, via OAI-PMH | Bulk metadata harvesting is the supported path. Full text is 2.9 TB in requester-pays S3; abstracts answer the question set. |
| Baseline chunking | Fixed 512-token windows | The thing to beat. It has to be in the repo or the comparison is a claim. |
| Challenger chunking | Section-aware, parent-child | Retrieve the small child, hand the model the parent section. |
| Vector index | pgvector HNSW | Better recall than IVFFlat without tuning probe counts per query. |
| Filtered search | Iterative index scans (pgvector 0.8+) | A date or category filter otherwise silently truncates results below k. |
| Lexical arm | Generated `tsvector` column + GIN | Exact terms and author names are where dense retrieval quietly loses. |
| Fusion | Reciprocal rank fusion, k=60 start | Fuses two rankings without calibrating two score scales against each other. |
| Question set | 100, hand-written from abstracts | See Tradeoff. |

## Tradeoff

**The question set is written by hand, and that is the expensive part.**

Generating questions with a model and grading answers with the same model
measures the model agreeing with itself. The number that comes out is real
arithmetic over meaningless inputs. So the 100 questions are written by a
person reading abstracts, several of them requiring two papers to answer, and
they are committed to the repo so anyone can check them.

The cost is a day of unglamorous work before any retrieval code is worth
running. The benefit is that every number below means something.

Second tradeoff: abstracts, not full text. Full-text retrieval over 2.9 TB
would be a different project with a different bottleneck (PDF extraction, not
retrieval quality). Abstracts keep the corpus honest and the iteration loop
short.

## Result

*Not yet measured. This section is filled in from `results/`, by the harness in
`evals/`, and not by hand — day 7 for retrieval, day 13 for the CI gate.*

| Metric | Baseline | Challenger | Delta |
|---|---|---|---|
| Hit rate @5 (100 hand-written questions) | — | — | — |
| Hit rate @5, hybrid RRF | — | — | — |
| Refusal rate (40 unanswerable) | — | — | — |
| Deliberate regression caught by CI | — | — | — |

**Target:** section-aware parent-child retrieval beats the fixed-window
baseline by 15 points of hit@5, hybrid adds a further 6, and a deliberate
chunk-overlap regression turns CI red before merge.

## Running it

```bash
make install         # editable install + dev tools
make db-up           # postgres 17 + pgvector on :5433
make harvest         # OAI-PMH harvest, resumable, ~6 months of cs.AI
make test            # no network required
```

The harvest is resumable by design: every page is appended to
`data/papers.jsonl` and the resumption token is checkpointed to
`.state/harvest.json` before the next request. Kill it at record 40,000 and it
picks up at record 40,000.

## Build log

`PLAN.md` has the day-by-day plan this repo is being built against, including
the numbers each day is supposed to produce.

## Limits

- Abstracts only. A question needing a figure, a table or a proof is out of scope.
- Single-node Postgres. No sharding, no replica, no serious concurrency story.
- The judge model in `evals/` is a cost line, not a free assertion. The suite
  runs a cheap subset per push and the full set nightly for that reason.
