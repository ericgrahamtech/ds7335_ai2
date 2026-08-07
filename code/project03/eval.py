import argparse
import json
import os

import duckdb

from pipeline import run_question, DB_PATH

REVENUE = "SUM(l_extendedprice * (1 - l_discount))"
LAST_WEEK = "BETWEEN current_date - 7 AND current_date - 1"
LAST_MONTH = "BETWEEN current_date - 30 AND current_date - 1"

GOLDEN = [
    ("How many orders were placed last week?",
     f"SELECT COUNT(*) FROM orders WHERE o_orderdate {LAST_WEEK}"),

    ("What was total revenue last week?",
     f"SELECT ROUND({REVENUE}, 2) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey WHERE o.o_orderdate {LAST_WEEK}"),

    ("How many customers do we have in each region?",
     "SELECT r.r_name, COUNT(*) FROM customer c JOIN nation n ON c.c_nationkey = n.n_nationkey JOIN region r ON n.n_regionkey = r.r_regionkey GROUP BY r.r_name"),

    ("What are the top 5 nations by revenue in the last 90 days?",
     f"SELECT n.n_name, ROUND({REVENUE}, 2) AS rev FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN customer c ON o.o_custkey = c.c_custkey JOIN nation n ON c.c_nationkey = n.n_nationkey WHERE o.o_orderdate BETWEEN current_date - 90 AND current_date - 1 GROUP BY n.n_name ORDER BY rev DESC LIMIT 5"),

    ("What was the average order value last month?",
     f"SELECT ROUND(AVG(o_totalprice), 2) FROM orders WHERE o_orderdate {LAST_MONTH}"),

    ("Which supplier nation has the highest average ship delay?",
     "SELECT n.n_name, ROUND(AVG(l.l_shipdate - o.o_orderdate), 2) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN supplier s ON l.l_suppkey = s.s_suppkey JOIN nation n ON s.s_nationkey = n.n_nationkey GROUP BY n.n_name ORDER BY 2 DESC LIMIT 1"),

    ("How many line items shipped in the last 30 days arrived late?",
     f"SELECT COUNT(*) FROM lineitem WHERE l_shipdate {LAST_MONTH} AND l_receiptdate > l_commitdate"),

    ("What was revenue by market segment last month?",
     f"SELECT c.c_mktsegment, ROUND({REVENUE}, 2) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN customer c ON o.o_custkey = c.c_custkey WHERE o.o_orderdate {LAST_MONTH} GROUP BY c.c_mktsegment"),

    ("What percentage of orders last month were high priority?",
     f"SELECT ROUND(100.0 * SUM(CASE WHEN o_orderpriority IN ('1-URGENT', '2-HIGH') THEN 1 ELSE 0 END) / COUNT(*), 2) FROM orders WHERE o_orderdate {LAST_MONTH}"),

    ("Who are our top 10 customers by lifetime revenue?",
     f"SELECT c.c_name, ROUND({REVENUE}, 2) AS rev FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN customer c ON o.o_custkey = c.c_custkey GROUP BY c.c_name ORDER BY rev DESC LIMIT 10"),

    ("What is the average number of line items per order?",
     "SELECT ROUND(AVG(cnt), 2) FROM (SELECT COUNT(*) AS cnt FROM lineitem GROUP BY l_orderkey)"),

    ("What was total revenue from the EUROPE region last month?",
     f"SELECT ROUND({REVENUE}, 2) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN customer c ON o.o_custkey = c.c_custkey JOIN nation n ON c.c_nationkey = n.n_nationkey JOIN region r ON n.n_regionkey = r.r_regionkey WHERE r.r_name = 'EUROPE' AND o.o_orderdate {LAST_MONTH}"),

    ("How many orders are currently open?",
     "SELECT COUNT(*) FROM orders WHERE o_orderstatus = 'O'"),

    ("Which part brand generated the most revenue last month?",
     f"SELECT p.p_brand, ROUND({REVENUE}, 2) AS rev FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN part p ON l.l_partkey = p.p_partkey WHERE o.o_orderdate {LAST_MONTH} GROUP BY p.p_brand ORDER BY rev DESC LIMIT 1"),

    ("How many suppliers do we have in each region?",
     "SELECT r.r_name, COUNT(*) FROM supplier s JOIN nation n ON s.s_nationkey = n.n_nationkey JOIN region r ON n.n_regionkey = r.r_regionkey GROUP BY r.r_name"),

    ("What is our overall return rate on line items?",
     "SELECT ROUND(100.0 * SUM(CASE WHEN l_returnflag = 'R' THEN 1 ELSE 0 END) / COUNT(*), 2) FROM lineitem"),

    ("What was the highest order total placed last week?",
     f"SELECT MAX(o_totalprice) FROM orders WHERE o_orderdate {LAST_WEEK}"),

    ("What is the average discount given on line items shipped last month?",
     f"SELECT ROUND(AVG(l_discount), 2) FROM lineitem WHERE l_shipdate {LAST_MONTH}"),

    ("What was revenue by customer nation last week?",
     f"SELECT n.n_name, ROUND({REVENUE}, 2) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey JOIN customer c ON o.o_custkey = c.c_custkey JOIN nation n ON c.c_nationkey = n.n_nationkey WHERE o.o_orderdate {LAST_WEEK} GROUP BY n.n_name"),

    ("How many distinct parts did we sell last month?",
     f"SELECT COUNT(DISTINCT l_partkey) FROM lineitem l JOIN orders o ON l.l_orderkey = o.o_orderkey WHERE o.o_orderdate {LAST_MONTH}"),
]


def norm_cell(v):
    try:
        return f"{round(float(v), 2):.2f}"
    except (TypeError, ValueError):
        return str(v)


def normalize(df):
    # column-order and column-name agnostic comparison
    rows = [tuple(sorted(norm_cell(v) for v in row)) for row in df.itertuples(index=False)]
    return sorted(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--no-semantic-layer", action="store_true")
    args = parser.parse_args()
    use_sl = not args.no_semantic_layer
    mode = "semantic" if use_sl else "baseline"

    con = duckdb.connect(DB_PATH, read_only=True)
    results = []
    for question, ref_sql in GOLDEN:
        expected = normalize(con.execute(ref_sql).df())
        r = run_question(question, model=args.model, use_semantic_layer=use_sl)
        if r["error"] or r["df"] is None:
            passed = False
        else:
            passed = normalize(r["df"]) == expected
        results.append({
            "question": question,
            "passed": passed,
            "sql": r["sql"],
            "error": r["error"],
            "latency": round(r["latency"], 2),
            "tokens": r["tokens"],
        })
        print(f"{'PASS' if passed else 'FAIL'}  {question}")
    con.close()

    n = len(results)
    n_pass = sum(r["passed"] for r in results)
    avg_latency = sum(r["latency"] for r in results) / n
    total_tokens = sum(r["tokens"] for r in results)
    print(f"\n{args.model} / {mode}: {n_pass}/{n} correct "
          f"({100 * n_pass / n:.0f}%), avg latency {avg_latency:.1f}s, {total_tokens} tokens")

    os.makedirs("eval_results", exist_ok=True)
    out = f"eval_results/{args.model}_{mode}.json"
    with open(out, "w") as f:
        json.dump({"model": args.model, "mode": mode, "accuracy": n_pass / n,
                   "avg_latency": avg_latency, "total_tokens": total_tokens,
                   "results": results}, f, indent=2)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
