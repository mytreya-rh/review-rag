from util import anthropic_client, CLAUDE_MODEL, exec_sql
import json, os, re
from datetime import datetime

CHUNK_SIZE = 5   # Adjustable: 20–40 works well


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(msg):
    print(f"[{datetime.now()}] {msg}")


# ------------------------------------------------------------
# Fenced-block cleanup
# ------------------------------------------------------------
def clean_output(text):
    text = text.replace("```json", "")
    text = text.replace("```JSON", "")
    text = text.replace("```", "")
    return text.strip()


# ------------------------------------------------------------
# Extract JSON array robustly
# ------------------------------------------------------------
def extract_json_array(text):
    cleaned = clean_output(text)

    start = cleaned.find("[")
    if start == -1:
        raise ValueError("❌ No '[' found in Claude output")

    depth = 0
    for i in range(start, len(cleaned)):
        c = cleaned[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start:i+1]
                return json.loads(candidate)

    raise ValueError("❌ No matching ']' found")


# ------------------------------------------------------------
# Load DB rows
# ------------------------------------------------------------
log("Loading rows from arch_items...")
rows = exec_sql("SELECT concerns, arch_summary, evidence FROM arch_items")
rows = list(rows)
log(f"Loaded {len(rows)} rows")


# ------------------------------------------------------------
# Chunk the rows
# ------------------------------------------------------------
def chunk(list_, size):
    for i in range(0, len(list_), size):
        yield list_[i:i+size]


all_guidelines = []
chunk_id = 0

for chunk_rows in chunk(rows, CHUNK_SIZE):
    chunk_id += 1
    log(f"Processing chunk {chunk_id} with {len(chunk_rows)} rows...")

    context = []
    for r in chunk_rows:
        context.append({
            "concerns": r.concerns,
            "summary": r.arch_summary,
            "evidence": r.evidence,
        })

    # prompt = (
    #     "You are a senior cloud-native architect.\n\n"
    #     "Given these PR-derived architectural signals, output ONLY a JSON array.\n"
    #     "No markdown. No explanations. Strict JSON.\n\n"
    #     "Each element must contain:\n"
    #     "  concern\n"
    #     "  guideline\n"
    #     "  rationale\n"
    #     "  examples\n\n"
    #     "Input data:\n"
    #     + json.dumps(context, indent=2)
    # )

    prompt = (
        "You are a senior cloud-native architect.\n\n"
        "Using the following PR-derived architectural signals, generate ONLY a JSON array.\n"
        "No markdown. No explanation. Only valid JSON.\n\n"
        "Each element MUST be an object with fields:\n"
        "  concern\n"
        "  guideline\n"
        "  rationale\n"
        "  examples\n\n"
        "HARD LENGTH LIMITS (do not exceed):\n"
        "- guideline: max 125 words\n"
        "- rationale: max 240 words\n"
        "- examples: max 430 words\n"
        "If needed, shorten aggressively. Do NOT produce long paragraphs.\n"
        "Output must always be a SMALL JSON array.\n\n"
        "Input data:\n"
        + json.dumps(context, indent=2)
    )
    log(f"Calling Claude for chunk {chunk_id}...")
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,      # safe because chunk is small
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text

    log(f"Extracting JSON from chunk {chunk_id}...")
    try:
        guidelines = extract_json_array(raw)
        log(f"Chunk {chunk_id}: extracted {len(guidelines)} guidelines")
        all_guidelines.extend(guidelines)
    except Exception as e:
        log(f"❌ Failed extracting JSON for chunk {chunk_id}")
        log(raw[:500])
        raise


# ------------------------------------------------------------
# Save final combined guidelines
# ------------------------------------------------------------
os.makedirs("data", exist_ok=True)
with open("data/guidelines.json", "w") as f:
    json.dump(all_guidelines, f, indent=2)

log(f"Saved {len(all_guidelines)} guidelines to data/guidelines.json")
log("=== Guidelines distillation complete ===")
