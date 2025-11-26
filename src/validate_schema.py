#!/usr/bin/env python3
import psycopg2
import os
from tabulate import tabulate


EXPECTED = {
    "repo": "text",
    "pr": "integer",
    "filepath": "text",
    "comment": "text",
    "diff": "text",
    "concerns": "jsonb",
    "arch_summary": "text",
    "evidence": "text",
    "embedding": "vector(768)",
}

PGVECTOR_URL = os.environ["PGVECTOR_URL"]

def get_schema():
    conn = psycopg2.connect(PGVECTOR_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, udt_name, character_maximum_length
        FROM information_schema.columns
        WHERE table_name='arch_items'
    """)
    rows = cur.fetchall()
    conn.close()

    schema = {}
    for name, data_type, udt, charlen in rows:
        if udt.startswith("vector"):
            schema[name] = f"vector(768)"
        else:
            schema[name] = data_type
    return schema

if __name__ == "__main__":
    try:
        actual = get_schema()
    except Exception as e:
        print("❌ Table arch_items does not exist or DB not reachable")
        print(e)
        exit(1)

    errors = []
    for col, expected_type in EXPECTED.items():
        actual_type = actual.get(col)
        if actual_type != expected_type:
            errors.append((col, expected_type, actual_type))

    if errors:
        print("\n❌ SCHEMA MISMATCHES FOUND:\n")
        print(tabulate(
            errors,
            headers=["Column", "Expected Type", "Actual Type"]
        ))
        print("\nRun: python src/migrate_schema.py to fix.")
    else:
        print("✅ Schema is valid.")
