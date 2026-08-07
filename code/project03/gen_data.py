import json

import duckdb

con = duckdb.connect("tpch.duckdb")
con.execute("INSTALL tpch; LOAD tpch;")
con.execute("CALL dbgen(sf=0.1)")

# TPC-H dates are 1992-1998. Shift everything so orders end yesterday,
# so questions like "last week" actually mean something. Ship/receipt dates
# trail orders by up to ~4 months, so a few land in the future -- harmless,
# since "last N days" filters never touch them.
offset = con.execute(
    "SELECT (current_date - 1) - max(o_orderdate) FROM orders"
).fetchone()[0]  # integer days

date_cols = {
    "orders": ["o_orderdate"],
    "lineitem": ["l_shipdate", "l_commitdate", "l_receiptdate"],
}
for table, cols in date_cols.items():
    for col in cols:
        con.execute(f"UPDATE {table} SET {col} = {col} + {offset} * INTERVAL 1 DAY")

# snapshot the schema the semantic layer was written against, for drift detection
rows = con.execute(
    "SELECT table_name, column_name, data_type FROM information_schema.columns "
    "ORDER BY table_name, ordinal_position"
).fetchall()
schema = {}
for t, c, d in rows:
    schema.setdefault(t, {})[c] = d
with open("schema_snapshot.json", "w") as f:
    json.dump(schema, f, indent=2)

con.close()
print(f"tpch.duckdb built, dates shifted forward {offset} days, schema snapshot saved")
