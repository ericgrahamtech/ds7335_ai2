# Lexicon

Ask your database questions in plain English — and trust the answers.

Lexicon is a conversational analytics app built on a **semantic layer**: a
human-authored YAML file defining tables, join paths, metric definitions, and date
conventions. The LLM never computes an answer. It writes SQL constrained by those
definitions; validators enforce the rails; the database computes every number; and
the SQL behind every answer is one click away.

Demo data is TPC-H (a standard, portable benchmark schema) styled as a fictional
wholesale distributor, *Meridian Supply Co.*

## Why

Pointing an LLM at a raw production schema fails: it guesses join paths, guesses
business definitions ("does *revenue* include tax?"), and produces plausible but
wrong SQL. The fix used by mature products (Snowflake Cortex Analyst, Databricks
Genie) is to define meanings once, in a reviewable file, and shrink the LLM's job
from "guess SQL against a schema" to "map a question onto definitions humans
already blessed." Lexicon is a small, transparent, vendor-neutral implementation
of that architecture — built to show how it works and where it breaks.

## The flow of one question

```
question → LLM (system prompt: rules + semantic layer YAML + compressed history)
        → SQL statement
        → validate (sqlglot AST: one statement, SELECT-only, allowlisted tables)
        → execute (read-only DuckDB connection)
        → narrate (2nd LLM call describes only the rows that came back)
```

Knowledge (the semantic layer) goes *in* the prompt. Enforcement (the validator,
the read-only connection) sits *after* the model, in code it can't influence.

## Features

- **Chat** — multi-turn conversation with follow-up resolution. History is
  compressed (recent turns verbatim, older turns collapse to SQL + row count) so
  context stays small; a sidebar gauge shows real context usage per call.
- **Saved Reports** — save any answer as a living report: the LLM crystallizes the
  follow-up into a standalone question, and the report stores intent (question) +
  implementation (SQL). Reports re-run their SQL fresh on every visit — relative
  dates stay relative, no LLM involved. Rename, reorder, delete, export CSV.
- **Chat history** — conversations persist across restarts as archives (result
  snapshots), distinct from reports, which stay live.
- **Schema drift handling (Admin tab)** — schema changes are detected by diffing an
  introspected snapshot; every verified query and saved report is EXPLAIN-tested
  against the live schema (deterministic breakage detection). An LLM drafts the
  semantic layer update; a human reviews the diff and accepts, rejects with a
  logged reason, or hand-edits. Accepted changes are versioned in a changelog;
  stale reports get a one-click "rebuild in chat" that recompiles their question
  against the current layer.
- **Eval harness** — 20 golden questions with hand-written reference SQL, scored on
  accuracy, latency, and tokens. Supports a 2x2: {haiku, sonnet} x {semantic
  layer, raw schema baseline}.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
python gen_data.py          # builds tpch.duckdb, dates shifted to the present
streamlit run app.py
```

Evaluate:

```bash
python eval.py --model claude-haiku-4-5
python eval.py --model claude-haiku-4-5 --no-semantic-layer   # baseline comparison
```

Demo a schema migration:

```bash
python demo_migration.py          # renames a column, adds another
python demo_migration.py --undo   # reset
```

## Project layout

| File | Purpose |
|---|---|
| `semantic_layer.yaml` | The source of business truth: tables, joins, metrics, conventions, verified queries |
| `pipeline.py` | Prompt assembly, LLM calls, SQL extraction, validation, execution |
| `app.py` | Streamlit UI: chat, saved reports, admin |
| `schema_check.py` | Schema snapshot/diff, EXPLAIN health checks, LLM update drafting, changelog |
| `eval.py` | Golden-question eval harness |
| `gen_data.py` | TPC-H generation + date shift + schema snapshot |
| `demo_migration.py` | Fake production migration for the drift demo |

## Governance model

Three separate controls: **capability** (sqlglot AST validation — whitelist by
shape, not a blacklist of verbs), **visibility** (table allowlist, enforced in
code, deliberately not derived from the LLM-editable YAML), and **meaning** (the
semantic layer itself, changed only through the human-review flow). Read-only is
enforced at three layers — prompt (a request), parser (a checkpoint), database
connection (the wall).

## Known limits

Single tables, no dashboards; no user accounts (state is local JSON, designed to
swap for per-user storage); no conversation compaction (designed, unneeded at
demo scale); eval is single-turn only; no query timeouts or row caps. The real
production cost isn't code — it's writing and governing the semantic layer, which
is organizational work no vendor can skip for you.

TPC-H is portable to any RDBMS, and sqlglot can transpile the generated SQL to
other dialects — nothing here is DuckDB-specific.

## Provenance

Built end-to-end with Claude (planning, architecture, code, tests) as a
demonstration of LLM-directed development for a graduate ML course.
