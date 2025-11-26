import os
import json
import re
from typing import List

from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from anthropic import AnthropicVertex

# -------------------------------------------------------------------
# DB
# -------------------------------------------------------------------

PGVECTOR_URL = os.environ["PGVECTOR_URL"]
engine = create_engine(PGVECTOR_URL, pool_pre_ping=True, future=True)

def exec_sql(sql: str, **params):
    """
    Simple helper to run SQL with optional named parameters.
    Returns a Result object.
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), params)

# -------------------------------------------------------------------
# Embeddings: all-mpnet-base-v2 (768 dims)
# -------------------------------------------------------------------

EMBED_MODEL = "all-mpnet-base-v2"
_embedder = SentenceTransformer(EMBED_MODEL)

def embed(texts: List[str]):
    """
    Compute embeddings for a list of strings.
    Returns a list of 768-dim vectors (Python lists of floats).
    """
    return _embedder.encode(texts, convert_to_numpy=True).tolist()

# -------------------------------------------------------------------
# Anthropic on Vertex
# -------------------------------------------------------------------

PROJECT = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
REGION = os.environ.get("CLOUD_ML_REGION", "global")

anthropic_client = AnthropicVertex(
    project_id=PROJECT,
    region=REGION,
)

# This is what your CLI reports
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5@20250929")

# -------------------------------------------------------------------
# Comment reduction
# -------------------------------------------------------------------

def reduce_comment(comment: str) -> str:
    """
    Strip code blocks, quoted bot sections, and compress whitespace.
    Keeps the core natural language signal for summarization.
    """
    c = comment
    # Remove fenced code blocks
    c = re.sub(r"```.*?```", "", c, flags=re.DOTALL)
    # Remove quoted lines (often bot noise)
    c = re.sub(r"^>.*$", "", c, flags=re.MULTILINE)
    # Collapse whitespace
    c = re.sub(r"\s+", " ", c).strip()
    return c

# -------------------------------------------------------------------
# Architectural summarization helpers
# -------------------------------------------------------------------

class summarize_arch:
    @staticmethod
    def classify_concerns(comment: str):
        """
        Ask Claude which architectural concerns apply to a comment.
        Returns a list of strings.
        """
        prompt = f"""
You are an experienced Kubernetes/OpenShift architect.

Given the following PR review comment, identify which architectural concerns apply.
Possible concerns (pick any that fit, or add your own if needed):

- upgrade-safety
- maintainability
- ease-of-use
- performance-tradeoff
- correctness
- extensibility
- api-compatibility
- validation-strictness
- config-safety

Return ONLY a JSON array of strings, e.g.:

["correctness", "upgrade-safety"]

Comment:
{comment}
"""

        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        out = resp.content[0].text.strip()
        # Try JSON parse, fall back to raw text
        try:
            return json.loads(out)
        except Exception:
            return [out]

    @staticmethod
    def generate_summary(diff: str, comment: str, concerns):
        """
        Produce a short architectural summary of why this comment matters.
        """
        prompt = f"""
You are an expert Kubernetes/OpenShift architectural reviewer.

Summarize the architectural significance of this PR review comment, focusing on:
- correctness
- upgrade-safety
- maintainability
- ease-of-use
- performance tradeoffs
- extensibility

Write 3–6 sentences, plain text, no bullet points, no JSON.

---
Diff context:
{diff}

---
Comment:
{comment}

---
Concerns (heuristic labels):
{concerns}
"""

        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()