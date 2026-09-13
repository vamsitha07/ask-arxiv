# Build plan

Two weeks, 2–3 commits a day. Week 1 is retrieval (project 01), week 2 is the
eval harness (project 02). Each day names the commits it should produce, so a
fresh session can read this file plus `git log` and know exactly where the
build stopped.

**Repo state is the source of truth.** If a day's commits are already in
`git log`, that day is done regardless of the date.

## Week 1 — retrieval

| Day | Date | Commits |
|---|---|---|
| 1 | Sat 12 Sep | `chore: scaffold project, deps and pgvector compose` · `feat(harvest): OAI-PMH harvester with resumption and checkpointing` · `docs: README with problem, decision, tradeoff and the plan` |
| 2 | Sun 13 Sep | `feat(db): papers and chunks schema with pgvector extension` · `feat(harvest): load JSONL into postgres idempotently` · `test: schema round-trip against a throwaway database` |
| 3 | Mon 14 Sep | `feat(chunk): fixed 512-token window baseline chunker` · `docs(evals): question set format and the first 20 hand-written questions` |
| 4 | Tue 15 Sep | `feat(chunk): section-aware parent-child chunker` · `feat(db): parent-child linkage on the chunks table` · `test: chunker boundary cases and parent id preservation` |
| 5 | Wed 16 Sep | `feat(embed): batched sentence-transformers embedding with resume` · `feat(index): HNSW index and iterative index scans for filtered search` |
| 6 | Thu 17 Sep | `feat(search): dense retrieval over pgvector` · `feat(search): tsvector GIN lexical arm` · `feat(search): reciprocal rank fusion at k=60` |
| 7 | Fri 18 Sep | `feat(evals): hit rate at k harness over the question set` · `docs: measured retrieval results, README Result table filled in` |

**Day 7 gate:** hit@5 for both chunking strategies is committed to `results/`
and the README Result table has real numbers in it.

## Week 2 — evals

| Day | Date | Commits |
|---|---|---|
| 8 | Sat 19 Sep | `feat(evals): split retrieval scoring from answer scoring` · `feat(evals): ragas context precision, recall, faithfulness, answer relevancy` · `chore(evals): eval config and run manifest` |
| 9 | Sun 20 Sep | `docs(evals): 40 unanswerable questions adjacent to the corpus` · `feat(evals): refusal rate as the headline metric` |
| 10 | Mon 21 Sep | `feat(evals): deterministic assertions for citation, length and format` · `feat(evals): judge calibration against 30 hand-graded outputs` · `docs: judge agreement rate and what disagreement means` |
| 11 | Tue 22 Sep | `ci: promptfoo eval action on pull requests with a pass/fail comment` · `ci: threshold gate that blocks the merge` |
| 12 | Wed 23 Sep | `ci: fast subset per push, full suite nightly` · `feat(evals): cheap judge model for the routine pass` · `docs: eval cost per run` |
| 13 | Thu 24 Sep | `test: deliberate chunk-overlap regression that CI must catch` · `revert: restore chunk overlap, with the red CI run linked` |
| 14 | Fri 25 Sep | `feat(app): minimal query API for the demo` · `ci: deploy to a free tier and publish the URL` · `docs: final README with both numbers and the demo link` |

**Day 14 gate:** a deliberate regression is on record turning CI red before
merge, the README opens with a live URL, and both numbers are measured.

## Rules for every day

1. Commits are real work, not padding. If a day's work is done in one commit,
   the day ships one commit.
2. No number goes in the README that was not produced by code in the repo.
3. Questions are written by a human. A model neither writes them nor grades
   the system that answers them alone.
4. Tests do not require the network. Fixtures for anything remote.

## How the nightly build session works

A fresh session runs at 20:00 America/New_York and has no memory of previous
days. Its contract:

1. Clone `https://github.com/vamsitha07/ask-arxiv` and read this file plus
   `git log --oneline`.
2. The next unbuilt day is the first row whose commits are not in the log.
3. Build that day's work in the clone. Tests and lint must pass before
   anything is packaged.
4. Ship two files: `ask-arxiv-day-NN.tar.gz` (the changed files) and
   `push-day-NN.sh`, which pulls, unpacks over the working tree, makes that
   day's commits with the local git identity, and pushes.

The build environment cannot reach `arxiv.org` or `huggingface.co`. Anything
that needs the live API or a model download is written, tested against
fixtures, and run on the developer's machine. No number reaches the README
that was not produced by a real run there.
