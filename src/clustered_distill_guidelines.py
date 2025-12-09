from util import anthropic_client, CLAUDE_MODEL, exec_sql
import json
import os
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans

# -------------------------------
# Logging helper
# -------------------------------

def log(msg: str) -> None:
    print(f"[{datetime.now()}] {msg}")


# -------------------------------
# Clean Claude output
# -------------------------------

def clean_output(text: str) -> str:
    """
    Remove ```json fences and stray backticks.
    """
    t = text.strip()
    for fence in ("```json", "```JSON", "```"):
        t = t.replace(fence, "")
    return t.strip()


def extract_json_object(text: str):
    """
    Robustly extract the first top-level JSON object from Claude output.
    """
    cleaned = clean_output(text)
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("❌ No '{' found in Claude output")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(cleaned)):
        c = cleaned[i]

        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue

        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                json_str = cleaned[start : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    print("❌ JSON decode failed. Raw slice:")
                    print(json_str[:500])
                    raise e

    raise ValueError("❌ No matching '}' found for top-level JSON object")


# -------------------------------
# Helpers for concerns & embeddings
# -------------------------------

def normalize_concerns(raw):
    """
    DB column 'concerns' may be stored as:
      - Python list
      - JSON string
      - plain string
    Normalize to a Python list of strings.
    """
    if raw is None:
        return []

    if isinstance(raw, list):
        return [str(x) for x in raw]

    if isinstance(raw, str):
        s = raw.strip()
        # Try JSON
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x) for x in arr]
            except Exception:
                pass
        # Fallback: single label
        return [s]

    # Last-resort
    return [str(raw)]


import json

def row_embedding(row):
    """
    Convert DB embedding to a Python list[float].

    Handles:
    - pgvector Vector type (iterable of floats)
    - JSON-encoded strings like "[0.1, 0.2, ...]"
    - Comma-separated strings like "0.1,0.2,..."
    """
    v = row.embedding
    if v is None:
        return None

    # Already a list/tuple?
    if isinstance(v, (list, tuple)):
        try:
            return [float(x) for x in v]
        except Exception:
            return None

    # String case: JSON or comma-separated
    if isinstance(v, str):
        s = v.strip()

        # JSON list, e.g. "[0.1, 0.2, ...]"
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [float(x) for x in arr]
            except Exception:
                pass

        # Fallback: comma-separated floats "0.1,0.2,..."
        try:
            return [float(x) for x in s.strip("[]{}()").split(",") if x.strip()]
        except Exception:
            return None

    # Fallback: treat as generic iterable (e.g. pgvector Vector)
    try:
        return [float(x) for x in v]
    except Exception:
        return None



# -------------------------------
# Cluster selection heuristic
# -------------------------------

def choose_n_clusters(n_points: int) -> int:
    """
    Simple heuristic for KMeans cluster count.
    """
    if n_points <= 10:
        return 3
    if n_points <= 40:
        return 5
    if n_points <= 120:
        return 7
    # cap to avoid silly many clusters
    return min(12, max(8, n_points // 20))


# -------------------------------
# Main
# -------------------------------

def main():
    log("\n=== Clustered Guidelines distillation run started ===")

    # 1) Load rows with embeddings
    log("Loading rows with embeddings from arch_items...")
    rows = list(
        exec_sql(
            """
            SELECT id, concerns, arch_summary, evidence, embedding
            FROM arch_items
            WHERE embedding IS NOT NULL
            """
        )
    )
    log(f"Loaded {len(rows)} rows")

    if not rows:
        log("No rows with embeddings found. Exiting.")
        return

    # Build embedding matrix + normalized items
    raw_embs = []
    raw_items = []

    for r in rows:
        v = row_embedding(r)
        if v is None:
            continue

        # Normalize to simple Python list[float]
        try:
            v_list = list(v)
        except TypeError:
            v_list = v

        # If we somehow get list of list, flatten one level
        if v_list and isinstance(v_list[0], (list, tuple)):
            flat = []
            for sub in v_list:
                flat.extend(sub)
            v_list = flat

        raw_embs.append(v_list)
        raw_items.append(
            {
                "id": r.id,
                "concerns": normalize_concerns(r.concerns),
                "summary": r.arch_summary or "",
                "evidence": r.evidence or "",
            }
        )

    if not raw_embs:
        log("No usable embeddings after normalization. Exiting.")
        return

    # Check dimensions and filter to the dominant one (likely 768)
    dim_counts = {}
    for v in raw_embs:
        dim_counts[len(v)] = dim_counts.get(len(v), 0) + 1

    log(f"Embedding dimension distribution: {dim_counts}")

    # Pick the dimension that occurs most often
    target_dim = max(dim_counts.items(), key=lambda kv: kv[1])[0]
    log(f"Using target embedding dimension: {target_dim}")

    embs = []
    items = []
    skipped = 0
    for v, it in zip(raw_embs, raw_items):
        if len(v) != target_dim:
            skipped += 1
            continue
        embs.append(v)
        items.append(it)

    log(f"Kept {len(embs)} items with dim={target_dim}, skipped {skipped} mismatched items.")

    if len(embs) < 2:
        log("Not enough consistent embedded items to cluster. Exiting.")
        return

    X = np.array(embs, dtype=float)
    n_points = X.shape[0]
    n_clusters = choose_n_clusters(n_points)
    log(f"Clustering {n_points} items into {n_clusters} clusters...")

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    # Group items by cluster label
    clusters = {}
    for item, label in zip(items, labels):
        clusters.setdefault(label, []).append(item)

    log(f"Formed {len(clusters)} clusters")

    all_guidelines = []

    # 2) For each cluster, call Claude to derive cluster-specific guidelines
    for label, cluster_items in clusters.items():
        log(f"\n--- Processing cluster {label} with {len(cluster_items)} items ---")

        MAX_ITEMS_PER_CLUSTER = 40
        if len(cluster_items) > MAX_ITEMS_PER_CLUSTER:
            cluster_items = cluster_items[:MAX_ITEMS_PER_CLUSTER]
            log(f"Cluster {label} truncated to {MAX_ITEMS_PER_CLUSTER} items for prompt")

        context = []
        for it in cluster_items:
            context.append(
                {
                    "id": it["id"],
                    "concerns": it["concerns"],
                    "summary": it["summary"],
                    "evidence": it["evidence"],
                }
            )

        prompt = (
            "You are a senior Kubernetes / OpenShift architect.\n\n"
            "You are given a cluster of PR review comments that are semantically similar.\n"
            "From these, derive *cluster-level* architectural guidelines.\n\n"
            "Requirements:\n"
            "- Focus ONLY on themes present in this cluster (do NOT invent unrelated topics).\n"
            "- Merge duplicate ideas into a single guideline where possible.\n"
            "- Be concrete and actionable (think of this as an internal architecture handbook).\n"
            "- Emphasize upgrade-safety, maintainability, ease-of-use, performance tradeoffs,\n"
            "  correctness, extensibility, and API/validation contracts as applicable.\n\n"
            "Output format:\n"
            "Return ONLY a JSON object with two fields. No markdown, no prose, no explanation.\n"
            "{\n"
            '  "cluster_name": "short-kebab-case-name describing the main theme (e.g., \'api-validation\', \'cel-rules\', \'upgrade-paths\')",\n'
            '  "guidelines": [\n'
            "    {\n"
            "      \"concern\": \"short label for the primary concern\",\n"
            "      \"guideline\": \"clear directive phrased as a rule\",\n"
            "      \"rationale\": \"2-4 sentences explaining why this matters\",\n"
            "      \"examples\": [\"concrete examples or patterns from the input situations\"]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Here is the input cluster data as JSON:\n\n"
            + json.dumps(context, indent=2)
        )

        log(f"Calling Claude for cluster {label}...")
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        log(f"Claude returned {len(raw)} characters for cluster {label}. Extracting JSON...")

        try:
            result = extract_json_object(raw)
        except Exception as e:
            log(f"❌ Failed to extract JSON for cluster {label}: {e}")
            log("Raw (first 500 chars):")
            log(raw[:500])
            continue

        # Extract cluster name and guidelines
        if not isinstance(result, dict):
            log(f"Cluster {label} returned non-dict JSON; skipping.")
            continue

        cluster_name = result.get("cluster_name", f"cluster-{label}")
        guidelines = result.get("guidelines", [])

        if not isinstance(guidelines, list):
            log(f"Cluster {label} guidelines field is not a list; wrapping.")
            guidelines = [guidelines]

        for g in guidelines:
            if isinstance(g, dict):
                g["cluster_id"] = cluster_name

        all_guidelines.extend(guidelines)
        log(f"Cluster {label} ('{cluster_name}'): extracted {len(guidelines)} guidelines")

    # 3) Save aggregated guidelines
    os.makedirs("data", exist_ok=True)
    out_path = "data/guidelines_clustered.json"

    with open(out_path, "w") as f:
        json.dump(all_guidelines, f, indent=2)

    log(f"\nSaved {len(all_guidelines)} guidelines to {out_path}")
    log("=== Clustered Guidelines distillation complete ===")



if __name__ == "__main__":
    main()