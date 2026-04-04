"""Fetch contributor stats from all NextCommunity repos and update the leaderboard."""

import os
import re
import sys
import urllib.error
import urllib.request
import json

ORG = "NextCommunity"
API_URL = "https://api.github.com"
README_PATH = os.path.join(os.path.dirname(__file__), "..", "profile", "README.md")
LEADERBOARD_START = "<!-- LEADERBOARD:START -->"
LEADERBOARD_END = "<!-- LEADERBOARD:END -->"

# Manual email-to-login mapping for contributors who commit with multiple
# email addresses that may not all be linked to their GitHub account.
# Add entries like: "alternate@example.com": "github_login"
EMAIL_ALIASES = {}


def gh_request(url, token=None):
    """Make an authenticated GitHub API request and return parsed JSON."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "NextCommunity-Leaderboard-Script",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = getattr(resp, "status", None)
            body = resp.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        message = f"GitHub API request failed with status {exc.code} for {url}"
        if error_body:
            message = f"{message}: {error_body}"
        raise urllib.error.URLError(message) from exc

    if status is not None and not 200 <= status < 300:
        raise urllib.error.URLError(
            f"GitHub API request returned unexpected status {status} for {url}"
        )

    if not body.strip():
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise urllib.error.URLError(
            f"Failed to decode JSON response from {url}: {exc}"
        ) from exc
def get_all_pages(url, token=None):
    """Paginate through all results for a GitHub API endpoint."""
    results = []
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}per_page=100&page={page}"
        data = gh_request(page_url, token)
        if isinstance(data, dict):
            msg = data.get("message", "Unknown error")
            raise urllib.error.URLError(
                f"Expected list response from {url}, got error: {msg}"
            )
        if not isinstance(data, list) or not data:
            break
        results.extend(data)
        if len(data) < 100:
            break
        page += 1
    return results


def fetch_repos(token=None):
    """Fetch all public repos for the organization.

    Raises urllib.error.URLError on API failure.
    """
    url = f"{API_URL}/orgs/{ORG}/repos?type=public"
    return get_all_pages(url, token)


def fetch_commits(repo_name, token=None):
    """Fetch all commits for a single repo.

    Raises urllib.error.URLError on API failure.
    """
    url = f"{API_URL}/repos/{ORG}/{repo_name}/commits"
    return get_all_pages(url, token)


def resolve_login_from_noreply(email):
    """Extract a GitHub login from a noreply email address.

    Handles both formats:
      - username@users.noreply.github.com
      - 12345678+username@users.noreply.github.com
    """
    if email.endswith("@users.noreply.github.com"):
        local = email.split("@")[0]
        if "+" in local:
            return local.split("+", 1)[1]
        return local
    return None


_CO_AUTHOR_RE = re.compile(
    r"^Co-authored-by:\s*.+?\s*<([^>]+)>\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_co_authors(message):
    """Extract co-author email addresses from ``Co-authored-by:`` trailers.

    Returns a list of lower-cased, stripped email addresses found in the
    commit message.
    """
    if not message:
        return []
    return [m.lower().strip() for m in _CO_AUTHOR_RE.findall(message)]


def build_leaderboard(token=None):
    """Aggregate contributor commits across all repos and return sorted list.

    Uses the Commits API to get every commit with its author email and GitHub
    login.  A two-pass approach builds an email-to-login mapping first, then
    counts commits per resolved identity so that multiple email addresses
    belonging to the same person are combined.

    Co-authors specified via ``Co-authored-by:`` trailers in commit messages
    each receive credit for the commit alongside the primary author.

    Raises urllib.error.URLError if the repo listing fails.
    Returns (sorted_contributors, had_errors) where had_errors indicates
    whether any per-repo API failures occurred.
    """
    repos = fetch_repos(token)
    had_errors = False

    # Collect (login_or_none, email, is_bot) for every commit across all repos.
    # Co-authors extracted from commit messages are added as separate entries
    # with login=None so they go through email→login resolution.
    all_commits = []
    # Track logins and emails identified as bots from API metadata so that
    # co-author entries resolving to the same identity are also excluded.
    bot_logins = set()
    bot_emails = set()

    for repo in repos:
        if repo.get("fork"):
            continue
        repo_name = repo["name"]
        print(f"Fetching commits for {repo_name}...")
        try:
            for commit_obj in fetch_commits(repo_name, token):
                gh_author = commit_obj.get("author")  # GitHub user info
                commit_detail = commit_obj.get("commit", {})
                git_author = commit_detail.get("author", {})
                email = (git_author.get("email") or "").lower().strip()

                login = None
                if gh_author and gh_author.get("login"):
                    login = gh_author["login"]

                is_bot = bool(
                    (gh_author and gh_author.get("type") == "Bot")
                    or (login and login.endswith("[bot]"))
                    or (
                        gh_author
                        and "/apps/" in (gh_author.get("html_url") or "")
                    )
                )

                if is_bot:
                    if login:
                        bot_logins.add(login.lower())
                    if email:
                        bot_emails.add(email)

                all_commits.append((login, email, is_bot))

                # Credit co-authors from Co-authored-by trailers
                message = commit_detail.get("message", "")
                for co_email in parse_co_authors(message):
                    if co_email != email:
                        all_commits.append((None, co_email, False))
        except urllib.error.URLError as exc:
            print(f"Warning: Failed to fetch commits for {repo_name}: {exc}")
            had_errors = True

    # --- Phase 1: build email → login mapping ---
    email_to_login = dict(EMAIL_ALIASES)

    for login, email, _ in all_commits:
        if not email:
            continue
        if login and email not in email_to_login:
            email_to_login[email] = login
        elif login and email in email_to_login and email_to_login[email] != login:
            print(
                f"Warning: email {email} maps to both "
                f"{email_to_login[email]} and {login}; keeping first"
            )
        elif not login and email not in email_to_login:
            resolved = resolve_login_from_noreply(email)
            if resolved:
                email_to_login[email] = resolved

    # --- Phase 2: count commits per resolved identity ---
    contributors = {}
    for login, email, is_bot in all_commits:
        if is_bot:
            continue

        resolved = login or email_to_login.get(email)
        if not resolved:
            continue

        # Skip bots: logins ending with [bot], logins identified as bots
        # from API metadata, or emails belonging to known bot accounts.
        if (
            resolved.endswith("[bot]")
            or resolved.lower() in bot_logins
            or email in bot_emails
        ):
            continue

        if resolved not in contributors:
            contributors[resolved] = {"commits": 0, "login": resolved}
        contributors[resolved]["commits"] += 1

    sorted_contributors = sorted(
        contributors.values(), key=lambda c: c["commits"], reverse=True
    )
    return sorted_contributors, had_errors


def generate_markdown(contributors):
    """Generate a markdown table from the leaderboard data."""
    lines = [
        "",
        '<div align="center">',
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
    lines.append("</div>")
    lines.append("")
    return "\n".join(lines)


def update_readme(leaderboard_md):
    """Update the profile README with the leaderboard content."""
    with open(README_PATH, "r", encoding="utf-8") as f:
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
    elif start_idx == -1 and end_idx == -1:
        new_content = (
            f"{content.rstrip()}\n\n"
            f"{LEADERBOARD_START}\n"
            f"{leaderboard_md}\n"
            f"{LEADERBOARD_END}\n"
        )
    else:
        print(f"Error: Mismatched leaderboard markers in {README_PATH}", file=sys.stderr)
        return

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {README_PATH}")


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set. API rate limits will be very low.")

    try:
        contributors, had_errors = build_leaderboard(token)
    except urllib.error.URLError as exc:
        print(f"Error: API failure while fetching data: {exc}", file=sys.stderr)
        sys.exit(1)

    if not contributors:
        if had_errors:
            print("Error: No contributors found due to API failures.", file=sys.stderr)
            sys.exit(1)
        print("No contributors found. The organization may have no public repos or contributors.")
        sys.exit(0)

    leaderboard_md = generate_markdown(contributors)
    update_readme(leaderboard_md)
    print(f"Leaderboard updated with {len(contributors)} contributors.")


if __name__ == "__main__":
    main()
