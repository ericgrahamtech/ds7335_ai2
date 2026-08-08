import os
import re
import time
from datetime import date

import duckdb
import sqlglot
from sqlglot import exp
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
_client = None


def client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client

DB_PATH = "tpch.duckdb"
ALLOWED_TABLES = {"orders", "lineitem", "customer", "supplier", "part", "partsupp", "nation", "region"}

SYSTEM = """You translate business questions into SQL for a DuckDB database.
Rules:
- If the question asks for actual data values (counts, totals, averages, lists of records),
  return exactly one SELECT statement inside a ```sql code block. No other text.
- If the question is conceptual -- about the business, the data model, available metrics,
  or definitions -- answer briefly in plain text using only the provided context. Never
  state or estimate numbers from the data in plain text; numbers must come from SQL.
- Only use the tables provided.
- Follow the metric definitions and date conventions exactly as written, when provided.
- If the question needs data these tables do not contain, return the comment -- CANNOT ANSWER."""

CHAT_RULES = """
Conversation rules:
- Prior SQL and results in this conversation are reference context only. Any number you
  report must come from SQL executed for the current question -- never repeat a number
  from memory of an earlier result.
- Resolve follow-up references ("that", "break it down by...") using the conversation,
  then write complete standalone SQL for the current question.
- If a follow-up specifies a new time period, it replaces the previous turn's time
  filter entirely."""

RECENT_TURNS = 2  # turns kept verbatim; older ones collapse to sql + row count
CONTEXT_WINDOW = 200_000  # claude context window, for usage display


def get_raw_schema(con):
    lines = []
    for t in sorted(ALLOWED_TABLES):
        cols = con.execute(f"DESCRIBE {t}").fetchall()
        col_str = ", ".join(f"{c[0]} {c[1]}" for c in cols)
        lines.append(f"{t}({col_str})")
    return "\n".join(lines)


def build_context(con, use_semantic_layer):
    if use_semantic_layer:
        with open("semantic_layer.yaml") as f:
            return f.read()
    return "Database schema:\n" + get_raw_schema(con)


def response_text(resp):
    # models with extended thinking return thinking blocks before the text block
    return "".join(b.text for b in resp.content if b.type == "text")


def extract_sql(text):
    m = re.search(r"```sql\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else None


def validate(sql):
    statements = sqlglot.parse(sql, read="duckdb")
    if len(statements) != 1:
        raise ValueError("expected exactly one statement")
    if not isinstance(statements[0], exp.Select):
        raise ValueError("only SELECT statements are allowed")
    tables = {t.name.lower() for t in statements[0].find_all(exp.Table)}
    # CTE names look like tables to sqlglot, exclude them
    ctes = {c.alias.lower() for c in statements[0].find_all(exp.CTE)}
    bad = tables - ctes - ALLOWED_TABLES
    if bad:
        raise ValueError(f"query uses disallowed tables: {bad}")


def render_history(history):
    # recent turns kept verbatim (sql + result preview), older ones compressed
    msgs = []
    n = len(history)
    for i, t in enumerate(history):
        msgs.append({"role": "user", "content": t["question"]})
        if t.get("error"):
            content = f"```sql\n{t['sql']}\n```\nERROR: {t['error']}" if t.get("sql") else f"ERROR: {t['error']}"
        elif t.get("sql") is None:
            content = t["answer"]  # conceptual turn
        elif i >= n - RECENT_TURNS:
            content = (f"```sql\n{t['sql']}\n```\n"
                       f"Result ({t['nrows']} rows, first 5 shown):\n{t['preview']}")
        else:
            content = f"```sql\n{t['sql']}\n```\n(returned {t['nrows']} rows)"
        msgs.append({"role": "assistant", "content": content})
    return msgs


def run_chat(question, history, model="claude-haiku-4-5", use_semantic_layer=True):
    start = time.time()
    con = duckdb.connect(DB_PATH, read_only=True)
    context = build_context(con, use_semantic_layer)
    con.close()
    system = f"{SYSTEM}\n{CHAT_RULES}\nToday's date: {date.today()}.\n\n{context}"
    messages = render_history(history) + [{"role": "user", "content": question}]
    resp = client().messages.create(model=model, max_tokens=1024, system=system, messages=messages)
    raw = response_text(resp)
    tokens = resp.usage.input_tokens + resp.usage.output_tokens
    sql = extract_sql(raw)
    result = {"question": question, "sql": sql, "tokens": tokens,
              "input_tokens": resp.usage.input_tokens,
              "error": None, "df": None, "answer": None}
    if sql is None:
        if "CANNOT ANSWER" in raw:
            result["error"] = "model declined: question not answerable from these tables"
        else:
            result["answer"] = raw.strip()  # conceptual question, answered from semantic layer
    elif "CANNOT ANSWER" in sql:
        result["error"] = "model declined: question not answerable from these tables"
    else:
        try:
            validate(sql)
            con = duckdb.connect(DB_PATH, read_only=True)
            result["df"] = con.execute(sql).df()
            con.close()
        except Exception as e:
            result["error"] = str(e)
    result["latency"] = time.time() - start
    return result


def run_question(question, model="claude-haiku-4-5", use_semantic_layer=True):
    # single-turn path, used by eval.py
    return run_chat(question, [], model=model, use_semantic_layer=use_semantic_layer)


def standalone_question(question, history, model="claude-haiku-4-5"):
    # rewrite a follow-up as a self-contained question so saved reports need no chat context
    if not history:
        return question
    convo = "\n".join(f"Q: {t['question']}" for t in history)
    resp = client().messages.create(
        model=model, max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"Earlier questions in this conversation:\n{convo}\n\n"
                       f"Rewrite this follow-up as one fully self-contained question. "
                       f"Return only the question:\n{question}",
        }],
    )
    return response_text(resp).strip()


def narrate(question, df, model="claude-haiku-4-5"):
    sample = df.head(100)
    note = f"\n(showing first 100 of {len(df)} rows)" if len(df) > 100 else ""
    resp = client().messages.create(
        model=model,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"Question: {question}\nQuery result ({len(df)} rows):\n"
                       f"{sample.to_string()}{note}\n\n"
                       f"Answer the question in one or two sentences using only this result.",
        }],
    )
    return response_text(resp)
