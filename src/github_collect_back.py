import os, requests, orjson as json
from typing import Dict, List


GH = "https://api.github.com"
HEADERS = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}


def _get(url, params=None):
    items, next_url = [], url
    while next_url:
        r = requests.get(next_url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        items += data if isinstance(data, list) else [data]
        next_url = r.links.get("next", {}).get("url")
        params = None
    return items


def fetch_pr_context(repo: str, pr_number: int) -> List[Dict]:
    # files & patches
    files = _get(f"{GH}/repos/{repo}/pulls/{pr_number}/files")
    patches_by_file = {f["filename"]: f.get("patch", "") for f in files}

    # review comments (file, position, body)
    review_comments = _get(f"{GH}/repos/{repo}/pulls/{pr_number}/comments")

    # issue-level discussion
    issue_comments = _get(f"{GH}/repos/{repo}/issues/{pr_number}/comments")
    issue_thread = [
        {"author": c["user"]["login"], "body": c["body"], "created_at": c["created_at"]}
        for c in issue_comments
    ]

    records = []
    for rc in review_comments:
        file_path = rc.get("path")
        patch = patches_by_file.get(file_path, "")
        # naive local context: include the entire file patch for the file.
        # (Optionally refine by parsing hunk headers + positions.)
        diff_context = patch[:4000]
        records.append({
            "repo": repo,
            "pr_number": pr_number,
            "file_path": file_path,
            "line_start": rc.get("original_line"),
            "line_end": rc.get("line"),
            "diff_context": diff_context,
            "comment_body": rc.get("body", ""),
            "thread_json": issue_thread,
        })
    return records


if __name__ == "__main__":
    import sys
    repo = sys.argv[1] # e.g. kubernetes-sigs/secrets-store-csi-driver
    pr = int(sys.argv[2]) # e.g. 1234
    recs = fetch_pr_context(repo, pr)
    os.makedirs("data", exist_ok=True)
    with open("data/pr_records.jsonl", "wb") as f:
        for r in recs:
            f.write(json.dumps(r))
            f.write(b"\n")
    print(f"wrote {len(recs)} records")
