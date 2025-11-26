#!/usr/bin/env python3
import json
import sys
import time
import os
from datetime import datetime
from util import exec_sql, embed, reduce_comment, summarize_arch
from util import anthropic_client, CLAUDE_MODEL

# -----------------------------
# Logging Setup
# -----------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(
    LOG_DIR, f"preprocess_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

def log(msg):
    print(msg, file=open(LOG_FILE, "a"))
    # Do NOT print to console — console remains clean


# -----------------------------
# Read input file
# -----------------------------
if len(sys.argv) < 2:
    print("Usage: python src/arch_preprocess.py data/pr_records.jsonl")
    sys.exit(1)

input_file = sys.argv[1]
start_total = time.time()

log(f"=== Preprocess run started at {datetime.now()} ===")
log(f"Input file: {input_file}")

# Read all records
records = []
t0 = time.time()
with open(input_file) as f:
    for line in f:
        records.append(json.loads(line))
log(f"Loaded {len(records)} records in {time.time() - t0:.3f}s")

# -----------------------------
# Step 1: Identify new records
# -----------------------------
t_start_find = time.time()
log("\n--- Step: Detecting new records ---")

from sqlalchemy import text
from util import engine

def find_new_records(records):
    """
    Uses temp table + JOIN to fetch already-existing rows.
    Returns only rows not present in arch_items.
    """
    with engine.begin() as conn:

        log("Creating temp table tmp_incoming...")
        sql = """
            CREATE TEMP TABLE tmp_incoming (
                repo TEXT,
                pr INTEGER,
                filepath TEXT,
                comment TEXT
            ) ON COMMIT DROP;
        """
        conn.execute(text(sql))

        log("Inserting rows into temp table...")
        ins_sql = """
            INSERT INTO tmp_incoming (repo, pr, filepath, comment)
            VALUES (:repo, :pr, :fp, :comment)
        """

        batch_start = time.time()
        for r in records:
            conn.execute(
                text(ins_sql),
                {
                    "repo": r["repo"],
                    "pr": r["pr_number"],
                    "fp": r["file_path"],
                    "comment": r["comment_body"],
                },
            )
        log(f"Inserted {len(records)} rows into temp table in {time.time() - batch_start:.3f}s")

        log("Querying for existing rows...")
        q = conn.execute(
            text("""
                SELECT t.repo, t.pr, t.filepath, t.comment
                FROM tmp_incoming t
                JOIN arch_items a
                  ON a.repo = t.repo
                 AND a.pr = t.pr
                 AND a.filepath = t.filepath
                 AND a.comment = t.comment
            """)
        )

        existing = {(row.repo, row.pr, row.filepath, row.comment) for row in q}
        log(f"Found {len(existing)} existing rows")

    # Filter out existing
    new = []
    for r in records:
        key = (r["repo"], r["pr_number"], r["file_path"], r["comment_body"])
        if key not in existing:
            new.append(r)

    return new


new_records = find_new_records(records)
log(f"New records detected: {len(new_records)}")
log(f"Time to detect new records: {time.time() - t_start_find:.3f}s")

# -----------------------------
# If no new records, exit fast
# -----------------------------
if not new_records:
    total = time.time() - start_total
    log("\nNo new records. Exiting.")
    log(f"Total runtime: {total:.3f}s")
    print("Found 0 new records\nNothing new.")
    sys.exit(0)

print(f"Found {len(new_records)} new records.")
log("\n--- Step: Processing new records with LLM + embeddings ---")

# -----------------------------
# Process each new record
# -----------------------------
processed = []
for idx, r in enumerate(new_records, start=1):
    log(f"\nProcessing record {idx}/{len(new_records)}")
    t_rec = time.time()

    # 1. Reduce comment
    reduced = reduce_comment(r["comment_body"])

    # 2. LLM classify concerns
    t_llm1 = time.time()
    concerns = summarize_arch.classify_concerns(reduced)
    log(f" classify_concerns(): {time.time() - t_llm1:.3f}s")

    # 3. LLM create summary
    t_llm2 = time.time()
    summary = summarize_arch.generate_summary(r["diff_context"], reduced, concerns)
    log(f" generate_summary(): {time.time() - t_llm2:.3f}s")

    # 4. Embeddings
    t_emb = time.time()
    embedding = embed([summary])[0]
    log(f" embed(): {time.time() - t_emb:.3f}s")

    processed.append({
        "repo": r["repo"],
        "pr": r["pr_number"],
        "filepath": r["file_path"],
        "comment": r["comment_body"],
        "diff": r["diff_context"],
        "concerns": json.dumps(concerns),
        "arch_summary": summary,
        "evidence": "",
        "embedding": embedding,
    })

    log(f"Total per-record time: {time.time() - t_rec:.3f}s")


# -----------------------------
# Insert new processed rows
# -----------------------------
log("\n--- Step: Insert processed items into DB ---")
t_ins = time.time()

ins_sql = """
    INSERT INTO arch_items
    (repo, pr, filepath, comment, diff, concerns, arch_summary, evidence, embedding)
    VALUES (:repo, :pr, :filepath, :comment, :diff, :concerns, :arch_summary, :evidence, :embedding)
"""

for item in processed:
    exec_sql(ins_sql, **item)

log(f"Inserted {len(processed)} items in {time.time() - t_ins:.3f}s")

# -----------------------------
# Final timing
# -----------------------------
total_time = time.time() - start_total
log(f"\n=== Finished at {datetime.now()} ===")
log(f"Total runtime: {total_time:.3f}s")

print(f"Done. Added {len(processed)} new records.")

print(f"Instrumentation log created at:\n  {LOG_FILE}")