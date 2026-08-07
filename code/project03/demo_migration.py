import argparse

import duckdb

# fake production migration for the demo: rename a column the app relies on, add a new one
parser = argparse.ArgumentParser()
parser.add_argument("--undo", action="store_true")
args = parser.parse_args()

con = duckdb.connect("tpch.duckdb")
if args.undo:
    con.execute("ALTER TABLE orders RENAME COLUMN o_priority TO o_orderpriority")
    con.execute("ALTER TABLE customer DROP COLUMN c_email")
    print("migration undone")
else:
    con.execute("ALTER TABLE orders RENAME COLUMN o_orderpriority TO o_priority")
    con.execute("ALTER TABLE customer ADD COLUMN c_email VARCHAR")
    print("applied: orders.o_orderpriority renamed to o_priority, customer.c_email added")
con.close()
