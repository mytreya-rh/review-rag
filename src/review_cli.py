import sys
import os
import re
import requests
import json
from anthropic import AnthropicVertex

GITHUB_API = "https://api.github.com"

# Initialize Anthropic client
PROJECT = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
REGION = os.environ.get("CLOUD_ML_REGION", "us-east5")
anthropic_client = AnthropicVertex(
    project_id=PROJECT,
    region=REGION,
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5@20250929")


def parse_github_pr_url(url):
    """
    Parse GitHub PR URL to extract owner, repo, and PR number.
    
    Supports formats:
    - https://github.com/owner/repo/pull/123
    - https://github.com/owner/repo/pull/123/files
    - github.com/owner/repo/pull/123
    """
    pattern = r'github\.com/([^/]+)/([^/]+)/pull/(\d+)'
    match = re.search(pattern, url)
    if not match:
        return None
    return {
        'owner': match.group(1),
        'repo': match.group(2),
        'pr_number': match.group(3)
    }


def fetch_pr_diff(owner, repo, pr_number, token=None):
    """
    Fetch the unified diff for a GitHub PR.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Accept": "application/vnd.github.v3.diff"  # Request diff format
    }
    if token:
        headers["Authorization"] = f"token {token}"
    
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ GitHub API failed: {resp.status_code}", file=sys.stderr)
        print(f"Response: {resp.text}", file=sys.stderr)
        sys.exit(1)
    
    return resp.text


def get_diff(input_arg):
    """
    Get diff content from either a file path or GitHub PR URL.
    """
    # Check if it's a GitHub URL
    if 'github.com' in input_arg and '/pull/' in input_arg:
        pr_info = parse_github_pr_url(input_arg)
        if not pr_info:
            print(f"❌ Invalid GitHub PR URL: {input_arg}", file=sys.stderr)
            sys.exit(1)
        
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("⚠️  Warning: GITHUB_TOKEN not set. API rate limits may apply.", file=sys.stderr)
        
        print(f"📥 Fetching PR #{pr_info['pr_number']} from {pr_info['owner']}/{pr_info['repo']}...", file=sys.stderr)
        diff = fetch_pr_diff(pr_info['owner'], pr_info['repo'], pr_info['pr_number'], token)
        print(f"✅ Fetched {len(diff)} characters of diff", file=sys.stderr)
        return diff
    else:
        # Treat as file path
        try:
            with open(input_arg) as f:
                return f.read()
        except FileNotFoundError:
            print(f"❌ File not found: {input_arg}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/review_cli.py <github-pr-url|diff-file>", file=sys.stderr)
        print("\nExamples:", file=sys.stderr)
        print("  python src/review_cli.py https://github.com/owner/repo/pull/123", file=sys.stderr)
        print("  python src/review_cli.py path/to/changes.diff", file=sys.stderr)
        sys.exit(1)
    
    input_arg = sys.argv[1]
    
    # Load guidelines
    with open("data/guidelines_clustered.json") as f:
        guidelines = json.load(f)
    
    # Get diff from URL or file
    diff = get_diff(input_arg)
    
    # Generate review
    prompt = f"""
You are an expert Kubernetes/OpenShift architect.

Using the following guidelines:
{json.dumps(guidelines, indent=2)}

Review this diff:
{diff}

Return a markdown architectural review.
"""
    
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    print(resp.content[0].text)
