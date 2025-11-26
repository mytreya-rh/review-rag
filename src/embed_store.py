import json
from util import embed, exec_sql

rows = exec_sql("SELECT id, repo, pr, filepath, comment, diff, arch_summary, evidence FROM arch_items WHERE embedding IS NULL")

for row in rows:
    # Build a snippet to embed
    snippet = f"""
Repo: {row.repo}
PR: {row.pr}
File: {row.filepath}

Comment: {row.comment}
Diff: {row.diff}

Architectural Summary: {row.arch_summary}
Evidence: {row.evidence}
"""

    vec = embed([snippet])[0]

    exec_sql(
        "UPDATE arch_items SET embedding = :vec WHERE id = :id",
        id=row.id,
        vec=vec,
    )
