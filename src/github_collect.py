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
    parser.add_argument("--repo", action="append", help="Repository to collect from (can specify multiple times)")
    parser.add_argument("--repos", help="Comma-separated list of repositories")
    parser.add_argument("--token", required=True)
    parser.add_argument("--pr", type=int, help="Specific PR number (only works with single repo)")
    parser.add_argument("--all-merged", action="store_true")
    parser.add_argument("--search-arch-prs", action="store_true")
    parser.add_argument("--output", default="data/pr_records.jsonl")
    args = parser.parse_args()

    # Build list of repositories
    repos = []
    if args.repo:
        repos.extend(args.repo)
    if args.repos:
        repos.extend([r.strip() for r in args.repos.split(",")])
    
    if not repos:
        print("Error: Must specify at least one repository via --repo or --repos")
        sys.exit(1)
    
    # Validate PR-specific operations
    if args.pr and len(repos) > 1:
        print("Error: --pr can only be used with a single repository")
        sys.exit(1)

    all_items = []

    for repo in repos:
        print(f"\n{'='*60}")
        print(f"Processing repository: {repo}")
        print(f"{'='*60}")
        
        repo_items = []

        if args.pr:
            repo_items.extend(collect_pr(repo, args.pr, args.token))

        if args.all_merged:
            merged = list_merged_prs(repo, args.token)
            print(f"Found {len(merged)} merged PRs in {repo}")
            for pr in merged:
                repo_items.extend(collect_pr(repo, pr["number"], args.token))

        if args.search_arch_prs:
            pr_numbers = search_arch_related_prs(repo, args.token)
            for pr_num in pr_numbers:
                repo_items.extend(collect_pr(repo, pr_num, args.token))
        
        print(f"Collected {len(repo_items)} items from {repo}")
        all_items.extend(repo_items)

    if not all_items:
        print("\nNo items collected.")
        sys.exit(0)

    with open(args.output, "w") as f:
        for it in all_items:
            f.write(json.dumps(it) + "\n")

    print(f"\n{'='*60}")
    print(f"Wrote {len(all_items)} records to {args.output}")
    print(f"From {len(repos)} repositories")
    print(f"{'='*60}")
