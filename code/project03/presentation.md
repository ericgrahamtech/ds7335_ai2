# Presentation Outline — Ask Your Database (15 min)

## 1. Intro (2 min)
- Business need: executives consume canned reports but always have ad hoc questions.
  Inspiration: CEO wants "how many closings last week in TN?" answered by AI.
- The tension: a language prediction machine vs. precise analytics. Auditors don't
  accept "the model said so." SQL is precise; LLMs are plausible.
- Thesis: don't let the LLM compute answers. Let it *write SQL*, constrain it hard,
  and make every answer auditable.
- **The ladder of naive options** (ask of each: where does the number come from,
  and who defined what it means?):
  1. *Paste a CSV into claude.ai*: data becomes tokens; the model does mental math
     over rows — confident, plausible, unreliable, and silent about it. Context
     limits truncate big files. Stale snapshot, no artifact to audit.
  2. *Point an agent (Cowork) at a spreadsheet*: better than people think — it writes
     and executes real code, so numbers are computed. But meanings are re-guessed
     every session (same question, different day, different answer), no rails
     (arbitrary code, not one validated SELECT), one exported file, nothing reusable.
     Great for exploration; not a regime.
  3. *Give the agent database credentials*: live data, real SQL, zero governance.
     Security nightmare (an LLM holding warehouse creds, prompt injection, results
     flowing into context), schema re-explored every session, no consistency, no
     saved artifacts. Can get right answers; can't promise them.
  4. *MCP (what my office tried)*: MCP is transport, not intelligence — it
     standardizes tool calls but says nothing about what's behind them. Slow (dozens
     of round trips rediscovering schema per question), wrong (guessed joins and
     definitions). None of that is MCP's fault or fixed by it. Proof: this app could
     be exposed AS an MCP server tomorrow — the value is the semantic layer and
     rails behind the endpoint, which no protocol provides.
  - One-liner: paste-in predicts numbers; agents compute numbers but guess meanings;
    credentials get real SQL without governance; MCP standardizes plumbing without
    adding knowledge. The semantic layer is where meaning gets written down.
- **Prior art (say this explicitly)**: this pattern is established and productized.
  Snowflake Cortex Analyst is the mature commercial version — you author a semantic
  model (YAML: tables, dimensions, measures, synonyms, verified queries) and its
  managed multi-stage pipeline does constrained text-to-SQL against Snowflake data,
  with governance/RBAC flowing through automatically. Databricks AI/BI Genie is the
  same category; dbt MetricFlow and open-source tools (Vanna, WrenAI) are adjacent.
  Positioning: "I'm not claiming novelty — I built the load-bearing ~300 lines of
  this architecture, vendor-neutral and fully inspectable, to understand what those
  products do, what you're paying for, and where the failure modes live." Their
  advantages: production hardening, warehouse-native governance, multi-turn repair,
  feedback loops, SLAs. This project's: transparency, any RDBMS, any LLM, and a
  built-in eval harness (which vendors don't ship — you have to verify accuracy on
  your own data anyway).

## 2. The solution (2.5 min)
- Architecture in one line: question → LLM + semantic layer → SQL → validate → execute
  → narrate. The model never touches data; the database computes every number.
- The flow of one prompt (two LLM calls total):
  1. User types a question
  2. App assembles call #1: system prompt (rules + today's date + semantic layer YAML)
     + compressed conversation history + the question
  3. LLM returns text containing a SQL statement — it only writes text
  4. App code (no LLM): extract SQL, validate — one statement, SELECT-only,
     allowlisted tables. The model never sees this checkpoint
  5. Execute on a read-only connection; the database computes the answer
  6. LLM call #2: question + first rows of the result → one-sentence narration
     (can only describe rows that actually came back)
  7. UI: narration + table + SQL in expander; turn joins the history
  Key point: knowledge (semantic layer) goes IN the prompt; enforcement (validator,
  read-only) sits AFTER the model, in code it can't influence.
- **Semantic layer** (the core idea): a human-authored YAML that is the source of
  business truth — table descriptions, join paths, metric definitions (revenue =
  `SUM(l_extendedprice * (1 - l_discount))`, never `o_totalprice` — it includes tax),
  date conventions ("last week" = 7 full days ending yesterday), and verified example
  queries. The LLM's job shrinks from "guess SQL against a raw schema" to "map a
  question onto definitions humans already blessed."
- **Validation rails**: sqlglot parses every generated query — exactly one statement,
  SELECT only, allowlisted tables only — executed on a read-only connection.
- Data: TPC-H (standard benchmark schema, portable to any RDBMS), generated in DuckDB,
  dates shifted to the present so "last week" is meaningful. Fictional company:
  Meridian Supply Co.
- (Optional, strongest evidence if time allows: eval harness — 20 golden questions,
  2x2 of {Haiku, Sonnet} x {semantic layer, raw schema}. Architecture beats model size.)

## 3. Live chat demo (4 min)
Run one of the conversation paths below. Narrate while it thinks:
- **Persistent conversation**: last 2 turns ride along verbatim (SQL + 5-row preview);
  older turns compress to SQL + row count. The semantic layer and today's date are
  re-sent fresh every turn. Anti-drift rule: any number reported must come from SQL
  executed *this* turn — prior results are reference only.
- Open the SQL expander once: "this is the audit trail — every answer is a query you
  can hand to an analyst."
- **Export to CSV** — every manager's favorite feature on the planet.
- **Context percentage** (personal cause): the sidebar bar is the API's real input
  token count vs. the 200k window. Watch it barely move — compression at work. Users
  who can read a context gauge are better users of every AI tool.

## 4. Save a report (2 min)
- Click Save Report: the LLM first rewrites the follow-up as a **standalone question**
  ("save = crystallize"). A report stores *intent* (the question) + *implementation*
  (the SQL) + the schema version it was built against + a SQL lineage. Name required.
- Saved Reports tab: re-runs the SQL fresh on every visit — always-relative dates, no
  LLM, instant. This is a self-serve SSRS: chat is the authoring tool, the report is
  the artifact. Contrast with chat history (sidebar): history is an *archive* of what
  was said; reports are *alive*.
- Workflow story: send the report's SQL to an analyst for validation, then promote it
  into the official reporting regime/dashboard.

## 5. Schema change demo (3 min)
Staging: make sure a saved report uses `o_orderpriority` (see checklist below).
- Run `python demo_migration.py` (renames o_orderpriority → o_priority, adds
  customer.c_email). Real life: production schemas change constantly.
- Admin → Check for schema changes. Narrate the split:
  - **Detection is programmatic**: schema snapshot diffed against live database.
  - **Breakage testing is programmatic**: every verified query and saved report is
    EXPLAIN-tested — broken ones surface with the exact error. Deterministic. SSRS
    can't do this; here it's free because every artifact is SQL.
  - **Meaning is human**: no program can know what a new column means. The LLM drafts
    the semantic layer update (marking unclear columns "TODO: confirm meaning"); a
    human reviews the diff and accepts / rejects with reason (logged) / hand-edits.
- Accept → changelog entry versions the layer → all reports flag stale; one is broken.
- Rebuild in chat: the report's standalone question + old SQL + only the schema changes
  since it was built are fed through the normal pipeline. Review the new SQL, click
  Update saved report — SQL replaced in place, old SQL kept in lineage.
- Punchline: schema changes invalidate *implementations*, never *intents*. Rebuilding
  is recompiling the question against the new layer, with a human at both checkpoints.

## 6. Outro — honest limits (1 min)
- Simple tables only; no dashboard/viz layer (natural next feature).
- No user accounts — reports and chats are local JSON, designed to swap for per-user
  storage.
- Very long conversations: compaction (summarize-and-hand-off) is designed but not
  built; context stays tiny in practice.
- Small things: archived chat tables are 200-row snapshots with flattened dtypes;
  eval is single-turn only; multi-turn eval is an open problem.
- The real production cost isn't the code — it's writing and governing the semantic
  layer. That's organizational work no vendor can skip for you.

## 7. Epilogue (30 sec)
- Per course philosophy: built entirely with Claude (Fable) — planning conversation,
  architecture decisions, code, tests, and this outline. A few hours of wall-clock
  time. The skill being demonstrated is directing the tool: constraining it,
  validating its output, and knowing what to check.

---

## Demo conversation paths (pick one)

**Path A — revenue drill-down (finance flavor)**
1. "How many orders did we place last week?" — warm-up, show the SQL expander
2. "What was our revenue last month by region?" — joins + the revenue definition
3. "Break that down by market segment, just for Europe" — follow-up resolution ("that")
4. "Show it as a monthly trend over the last 6 months" — polished result → Export CSV
   → Save Report as "Europe Segment Revenue Trend"

**Path B — supplier performance (ops flavor, closest to the title/escrow turn-time analog)**
1. "Which supplier nations have the highest average ship delay?" — layer defines delay
2. "How many line items arrived late in the last 30 days?" — "late" = receipt after
   commit date, a definition the raw schema can't provide
3. "Break the late shipments down by supplier nation" — follow-up resolution
4. "What share of each nation's total shipments arrived late?" — percentage convention
   → Export CSV → Save Report as "Late Shipment Rate by Supplier Nation"

## Staging checklist (before recording)
- [ ] `python gen_data.py` fresh (dates end yesterday, snapshot written)
- [ ] Delete leftover reports.json / chats.json / schema_changelog.json for a clean slate
- [ ] Save the migration victim: ask "What percentage of orders last week were high
      priority?" → save as "High Priority Order Rate" (uses o_orderpriority — this is
      the report that *breaks* in section 5; your Path A/B report only goes *stale* —
      the broken-vs-stale contrast is a demo beat, point it out)
- [ ] Rehearse the chosen path once; relative dates mean numbers change daily
- [ ] `python demo_migration.py --undo` resets between takes (also re-run gen_data.py
      if you accepted a semantic layer change during rehearsal — restore the YAML from git)
- [ ] Keep terminal visible when running the migration — seeing it is the point
