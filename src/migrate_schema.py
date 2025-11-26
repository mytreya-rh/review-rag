#!/usr/bin/env python3
import psycopg2
import os

PGVECTOR_URL = os.environ["PGVECTOR_URL"]

EXPECTED = {
    "repo": "TEXT",
    "pr": "INTEGER",
    "filepath": "TEXT",
    "comment": "TEXT",
    "diff": "TEXT",
    "concerns": "JSONB",
    "arch_summary": "TEXT",
    "evidence": "TEXT",
    "embedding": "VECTOR(768)",
}

def ensure_extension(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

def table_exists(cur):
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name='arch_items'
        );
    """)
    return cur.fetchone()[0]

def create_table(cur):
    cur.execute("""
        CREATE TABLE arch_items (
            id SERIAL PRIMARY KEY,
            repo TEXT,
            pr INTEGER,
            filepath TEXT,
            comment TEXT,
            diff TEXT,
            concerns JSONB,
            arch_summary TEXT,
            evidence TEXT,
            embedding VECTOR(768)
        );
    """)

def fix_column_type(cur, col, want):
    print(f"🔧 Fixing column {col} → {want}")
    if want.startswith("VECTOR"):
        cur.execute(f"ALTER TABLE arch_items ALTER COLUMN {col} TYPE {want};")
    else:
        cur.execute(f"""
            ALTER TABLE arch_items 
            ALTER COLUMN {col} 
            TYPE {want} USING {col}::{want};
        """)

def migrate():
    conn = psycopg2.connect(PGVECTOR_URL)
    cur = conn.cursor()

    ensure_extension(cur)

    if not table_exists(cur):
        print("⚠️ arch_items missing → creating table")
        create_table(cur)
        conn.commit()
        print("✅ Table created")
        return

    # Fetch actual schema
    cur.execute("""
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_name='arch_items';
    """)
    rows = cur.fetchall()
    actual = {}
    for col, data_type, udt in rows:
        if udt.startswith("vector"):
            actual[col] = "VECTOR(1536)"
        else:
            actual[col] = data_type.upper()

    # Fix mismatches
    for col, want_type in EXPECTED.items():
        if col not in actual:
            print(f"➕ Adding missing column: {col}")
            cur.execute(f"ALTER TABLE arch_items ADD COLUMN {col} {want_type};")
            continue

        if actual[col] != want_type:
            fix_column_type(cur, col, want_type)

    conn.commit()
    conn.close()
    print("✅ Migration complete")

if __name__ == "__main__":
    migrate()
