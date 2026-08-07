# Ask Your Database: Semantic-Layer Text-to-SQL

## Problem

Executives want to ask a database questions in plain English ("how many orders did
we do last week in Europe?") and trust the answer. Pointing an LLM at a raw schema
fails: it guesses join paths, guesses business definitions, and produces plausible
but wrong SQL. The fix used by industry tools (Snowflake Cortex Analyst, Databricks
Genie) is a **semantic layer**: metrics, join paths, and date conventions defined
once by humans, with the LLM constrained to map questions onto them.

## Architecture

```
question -> prompt (semantic layer YAML) -> Claude -> SQL
        -> validate (sqlglot: single SELECT, allowed tables only)
        -> execute (read-only DuckDB) -> result + narration
```

Key property for auditability: the LLM never computes an answer. It only writes
SQL, which is displayed and logged. The database computes the answer.

## Components

- `gen_data.py` — generates TPC-H (sf=0.1) via DuckDB, shifts all dates so the
  data ends yesterday (makes "last week" questions meaningful)
- `semantic_layer.yaml` — table descriptions, join paths, metric definitions
  (e.g. revenue = SUM(l_extendedprice * (1 - l_discount))), date conventions,
  verified example queries
- `pipeline.py` — prompt construction, Claude call, SQL extraction, validation,
  execution. Baseline mode uses raw schema only (no semantic layer) for comparison
- `eval.py` — 20 golden questions with hand-written reference SQL. Compares
  LLM-generated results against reference results. Flags: `--model`,
  `--no-semantic-layer`
- `app.py` — Streamlit demo

## Evaluation design

2x2: {haiku, sonnet} x {semantic layer, raw schema}, scored on accuracy,
latency, and tokens. Hypothesis: the semantic layer matters more than model size.

## Non-goals

No auth, no multi-turn conversation, no write queries, no dialect support beyond
DuckDB (though sqlglot can transpile the generated SQL to any dialect, and TPC-H
itself is portable to any RDBMS).
