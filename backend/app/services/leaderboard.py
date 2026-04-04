"""Core leaderboard aggregation service.

Async reimplementation of ``scripts/leaderboard.py``'s ``build_leaderboard``
logic using httpx for non-blocking GitHub API access.
"""

from __future__ import annotations

import re
from collections import namedtuple
from datetime import date, timedelta

from backend.app.services.achievements import get_achievements
from backend.app.services.github_client import fetch_commits, fetch_repos
from backend.app.services.levels import (
    build_levels_lookup,
    compute_level,
    compute_peak_rarity,
    fetch_levels_json,
    sorted_level_keys,
)

SITE_REPO_NAME = "NextCommunity.github.io"
DOTGITHUB_REPO_NAME = ".github"

# Manual email-to-login mapping.
EMAIL_ALIASES: dict[str, str] = {}

CommitRecord = namedtuple(
    "CommitRecord",
    ["login", "email", "is_bot", "repo_name", "commit_date", "is_coauthor"],
)

_CO_AUTHOR_RE = re.compile(
    r"^Co-authored-by:\s*.+?\s*<([^>]+)>\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# --- Points configuration ---
POINTS_CONFIG: dict = {
    "per_commit": 10,
    "per_streak_day": 5,
    "per_achievement": 15,
    "per_extra_repo": 20,
    "rarity_bonus": {
        "common": 0,
        "uncommon": 10,
        "rare": 25,
        "epic": 50,
        "legendary": 100,
        "mythic": 200,
        "absolute": 500,
    },
}


def parse_co_authors(message: str) -> list[str]:
    """Extract co-author email addresses from ``Co-authored-by:`` trailers."""
    if not message:
        return []
    return [m.lower().strip() for m in _CO_AUTHOR_RE.findall(message)]


def resolve_login_from_noreply(email: str) -> str | None:
    """Extract a GitHub login from a noreply email address."""
    if email.endswith("@users.noreply.github.com"):
        local = email.split("@")[0]
        if "+" in local:
            return local.split("+", 1)[1]
        return local
    return None


def compute_longest_streak(commit_dates: set[date]) -> int:
    """Return the longest consecutive-day commit streak from a set of dates."""
    if not commit_dates:
        return 0
    sorted_dates = sorted(set(commit_dates))
    longest = 1
    current = 1
    for prev, cur in zip(sorted_dates, sorted_dates[1:]):
        if cur - prev == timedelta(days=1):
            current += 1
            longest = max(longest, current)
        elif cur - prev > timedelta(days=1):
            current = 1
    return longest


def compute_points(contributor: dict) -> int:
    """Return a gamified point total for a contributor."""
    cfg = POINTS_CONFIG
    pts = contributor["commits"] * cfg["per_commit"]
    pts += contributor["longest_streak"] * cfg["per_streak_day"]
    pts += len(contributor["achievements"]) * cfg["per_achievement"]
    extra_repos = max(contributor["repos_count"] - 1, 0)
    pts += extra_repos * cfg["per_extra_repo"]
    pts += cfg["rarity_bonus"].get(
        contributor.get("peak_rarity", "common"), 0,
    )
    return pts


async def build_leaderboard() -> tuple[list[dict], bool, list[dict]]:
    """Aggregate contributor commits across all repos and return sorted list.

    Returns ``(sorted_contributors, had_errors, levels_data)``.
    """
    repos = await fetch_repos()
    had_errors = False

    all_commits: list[CommitRecord] = []
    bot_logins: set[str] = set()
    bot_emails: set[str] = set()

    for repo in repos:
        if repo.get("fork"):
            continue
        repo_name = repo["name"]
        try:
            for commit_obj in await fetch_commits(repo_name):
                gh_author = commit_obj.get("author")
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

                commit_date_str = git_author.get("date", "")
                commit_date = None
                if commit_date_str:
                    try:
                        commit_date = date.fromisoformat(
                            commit_date_str[:10]
                        )
                    except ValueError:
                        pass

                all_commits.append(CommitRecord(
                    login=login,
                    email=email,
                    is_bot=is_bot,
                    repo_name=repo_name,
                    commit_date=commit_date,
                    is_coauthor=False,
                ))

                message = commit_detail.get("message", "")
                for co_email in parse_co_authors(message):
                    if co_email != email and co_email not in bot_emails:
                        all_commits.append(CommitRecord(
                            login=None,
                            email=co_email,
                            is_bot=False,
                            repo_name=repo_name,
                            commit_date=commit_date,
                            is_coauthor=True,
                        ))
        except Exception:
            had_errors = True

    # Phase 1: email → login mapping
    email_to_login: dict[str, str] = dict(EMAIL_ALIASES)
    for rec in all_commits:
        if not rec.email:
            continue
        if rec.login and rec.email not in email_to_login:
            email_to_login[rec.email] = rec.login
        elif not rec.login and rec.email not in email_to_login:
            resolved = resolve_login_from_noreply(rec.email)
            if resolved:
                email_to_login[rec.email] = resolved

    # Phase 2: count commits per resolved identity
    contributors: dict[str, dict] = {}
    for rec in all_commits:
        if rec.is_bot:
            continue
        resolved = rec.login or email_to_login.get(rec.email)
        if not resolved:
            continue
        if (
            resolved.endswith("[bot]")
            or resolved.lower() in bot_logins
            or rec.email in bot_emails
        ):
            continue

        if resolved not in contributors:
            contributors[resolved] = {
                "commits": 0,
                "authored_commits": 0,
                "coauthored_commits": 0,
                "site_commits": 0,
                "dotgithub_commits": 0,
                "login": resolved,
                "repos": set(),
                "commit_dates": set(),
            }
        contributors[resolved]["commits"] += 1
        if rec.is_coauthor:
            contributors[resolved]["coauthored_commits"] += 1
        else:
            contributors[resolved]["authored_commits"] += 1
        contributors[resolved]["repos"].add(rec.repo_name)
        if rec.commit_date is not None:
            contributors[resolved]["commit_dates"].add(rec.commit_date)
        if rec.repo_name == SITE_REPO_NAME:
            contributors[resolved]["site_commits"] += 1
        elif rec.repo_name == DOTGITHUB_REPO_NAME:
            contributors[resolved]["dotgithub_commits"] += 1

    # Fetch canonical level definitions
    levels_data = await fetch_levels_json()
    levels_lookup = build_levels_lookup(levels_data)
    sk = sorted_level_keys(levels_lookup)

    # Compute gamification stats for each contributor
    for contrib in contributors.values():
        contrib["repos_count"] = len(contrib["repos"])
        contrib["repo_names"] = sorted(contrib["repos"])
        contrib["longest_streak"] = compute_longest_streak(
            contrib["commit_dates"]
        )
        level_info = compute_level(
            contrib["commits"], levels_lookup, _sorted_keys=sk,
        )
        contrib["level_num"] = level_info.get("level", 0)
        contrib["level_emoji"] = level_info.get("emoji", "🐣")
        contrib["level_title"] = level_info.get("name", "Newbie")
        contrib["level_rarity"] = level_info.get("rarity", "common")
        contrib["level_description"] = level_info.get("description", "")
        contrib["level_color"] = level_info.get("color", "#94a3b8")
        contrib["peak_rarity"] = compute_peak_rarity(
            contrib["commits"], levels_lookup, _sorted_keys=sk,
        )
        contrib["achievements"] = get_achievements(contrib)
        contrib["points"] = compute_points(contrib)
        # Remove non-serializable fields
        del contrib["repos"]
        del contrib["commit_dates"]

    sorted_contributors = sorted(
        contributors.values(), key=lambda c: c["commits"], reverse=True
    )
    return sorted_contributors, had_errors, levels_data
