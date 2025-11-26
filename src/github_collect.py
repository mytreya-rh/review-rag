#!/usr/bin/env python3
import requests
import argparse
import json
import sys
from datetime import datetime

GITHUB_API = "https://api.github.com"

ARCH_KEYWORDS = [
    "refactor", "design", "architecture", "api", "crd",
    "breaking", "upgrade", "validation", "performance",
    "scalability", "operator", "tech debt", "backward", "compat"
]

def gh(url, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print("GitHub API failed:", resp.status_code, resp.text)
        sys.exit(1)
    return resp.json()

def pr_matches_keywords(pr):
    text = (pr.get("title","") + " " +
            pr.get("body","")).lower()

    return any(k in text for k in ARCH_KEYWORDS)

def relevant_comment(comment_body):
    if not comment_body:
        return False
    text = comment_body.lower()
    return any(k in text for k in ARCH_KEYWORDS)

def collect_pr(repo, pr_number, token):
    print(f"Collecting PR #{pr_number} ...")

    pr_url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    pr = gh(pr_url, token)

    comments = gh(pr_url + "/comments", token)
    reviews = gh(pr_url + "/reviews", token)
    review_comments = gh(pr_url + "/comments", token)

    diff = requests.get(pr_url, headers={"Authorization": f"token {token}"},
                        params={"accept": "application/vnd.github.diff"}).text

    items = []

    for c in review_comments:
        body = c.get("body", "") or ""
        if not relevant_comment(body):
            continue

        item = {
            "repo": repo,
            "pr_number": pr_number,
            "file_path": c.get("path"),
            "line_start": c.get("original_line"),
            "line_end": c.get("line"),
            "diff_context": "",  # optional enhancement
            "comment_body": body,
            "thread_json": c,
        }
        items.append(item)

    return items

def list_merged_prs(repo, token):
    out = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{repo}/pulls?state=closed&per_page=100&page={page}"
        prs = gh(url, token)
        if not prs:
            break
        for pr in prs:
            if pr.get("merged_at"):
                out.append(pr)
        page += 1
    return out

def search_arch_related_prs(repo, token):
    """Use multiple queries to bypass the GitHub search operator limit."""

    groups = [
        ["refactor", "design", "architecture", "breaking", "upgrade"],
        ["api", "crd", "validation", "backward", "compat"],
        ["performance", "scalability", "operator", "tech debt"]
    ]

    pr_numbers = set()

    for group in groups:
        query = "+OR+".join(group)
        url = f"{GITHUB_API}/search/issues?q=repo:{repo}+is:pr+is:merged+({query})"
        result = gh(url, token)

        for item in result.get("items", []):
            pr_numbers.add(item["number"])

    print(f"Found {len(pr_numbers)} PRs across grouped keyword searches")
    return list(pr_numbers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--all-merged", action="store_true")
    parser.add_argument("--search-arch-prs", action="store_true")
    parser.add_argument("--output", default="data/pr_records.jsonl")
    args = parser.parse_args()

    all_items = []

    if args.pr:
        all_items.extend(collect_pr(args.repo, args.pr, args.token))

    if args.all_merged:
        merged = list_merged_prs(args.repo, args.token)
        for pr in merged:
            all_items.extend(collect_pr(args.repo, pr["number"], args.token))

    if args.search_arch_prs:
        pr_numbers = search_arch_related_prs(args.repo, args.token)
        for pr_num in pr_numbers:
            all_items.extend(collect_pr(args.repo, pr_num, args.token))

    if not all_items:
        print("No items collected.")
        sys.exit(0)

    with open(args.output, "w") as f:
        for it in all_items:
            f.write(json.dumps(it) + "\n")

    print("Wrote", len(all_items), "records to", args.output)
