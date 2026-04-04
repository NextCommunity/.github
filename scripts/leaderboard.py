"""Fetch contributor stats from all NextCommunity repos and update the leaderboard."""

import os
import sys
import urllib.error
import urllib.request
import json

ORG = "NextCommunity"
API_URL = "https://api.github.com"
README_PATH = os.path.join(os.path.dirname(__file__), "..", "profile", "README.md")
LEADERBOARD_START = "<!-- LEADERBOARD:START -->"
LEADERBOARD_END = "<!-- LEADERBOARD:END -->"


def gh_request(url, token=None):
    """Make an authenticated GitHub API request and return parsed JSON."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_all_pages(url, token=None):
    """Paginate through all results for a GitHub API endpoint."""
    results = []
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}per_page=100&page={page}"
        data = gh_request(page_url, token)
        if not data:
            break
        results.extend(data)
        if len(data) < 100:
            break
        page += 1
    return results


def fetch_repos(token=None):
    """Fetch all public repos for the organization."""
    url = f"{API_URL}/orgs/{ORG}/repos?type=public"
    try:
        return get_all_pages(url, token)
    except urllib.error.URLError as exc:
        print(f"Error: Failed to fetch repositories: {exc}", file=sys.stderr)
        return []


def fetch_contributors(repo_name, token=None):
    """Fetch contributors for a single repo."""
    url = f"{API_URL}/repos/{ORG}/{repo_name}/contributors?anon=0"
    try:
        return get_all_pages(url, token)
    except urllib.error.URLError as exc:
        print(f"Warning: Failed to fetch contributors for {repo_name}: {exc}")
        return []


def build_leaderboard(token=None):
    """Aggregate contributor commits across all repos and return sorted list."""
    repos = fetch_repos(token)
    contributors = {}

    for repo in repos:
        if repo.get("fork"):
            continue
        repo_name = repo["name"]
        print(f"Fetching contributors for {repo_name}...")
        for contrib in fetch_contributors(repo_name, token):
            login = contrib.get("login", "")
            if not login or contrib.get("type") == "Bot":
                continue
            if login not in contributors:
                contributors[login] = {"commits": 0, "login": login}
            contributors[login]["commits"] += contrib.get("contributions", 0)

    sorted_contributors = sorted(
        contributors.values(), key=lambda c: c["commits"], reverse=True
    )
    return sorted_contributors


def generate_markdown(contributors):
    """Generate a markdown table from the leaderboard data."""
    lines = [
        "",
        "## 🏆 Organization Leaderboard",
        "",
        "| Rank | Contributor | Commits |",
        "|------|-------------|---------|",
    ]
    for i, contrib in enumerate(contributors, start=1):
        login = contrib["login"]
        commits = contrib["commits"]
        lines.append(f"| {i} | [@{login}](https://github.com/{login}) | {commits} |")
    lines.append("")
    return "\n".join(lines)


def update_readme(leaderboard_md):
    """Update the profile README with the leaderboard content."""
    with open(README_PATH, "r") as f:
        content = f.read()

    start_idx = content.find(LEADERBOARD_START)
    end_idx = content.find(LEADERBOARD_END, start_idx) if start_idx != -1 else -1
    if start_idx != -1 and end_idx != -1:
        before = content[:start_idx]
        after = content[end_idx + len(LEADERBOARD_END) :]
        new_content = (
            f"{before}{LEADERBOARD_START}\n"
            f"{leaderboard_md}\n"
            f"{LEADERBOARD_END}{after}"
        )
    else:
        new_content = (
            f"{content}\n"
            f"{LEADERBOARD_START}\n"
            f"{leaderboard_md}\n"
            f"{LEADERBOARD_END}\n"
        )

    with open(README_PATH, "w") as f:
        f.write(new_content)

    print(f"Updated {README_PATH}")


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set. API rate limits will be very low.")

    contributors = build_leaderboard(token)
    if not contributors:
        print("No contributors found.", file=sys.stderr)
        sys.exit(1)

    leaderboard_md = generate_markdown(contributors)
    update_readme(leaderboard_md)
    print(f"Leaderboard updated with {len(contributors)} contributors.")


if __name__ == "__main__":
    main()
