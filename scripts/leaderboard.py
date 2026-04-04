"""Fetch contributor stats from all NextCommunity repos and update the leaderboard."""

import os
import re
import sys
import urllib.error
import urllib.request
import json
from bisect import bisect_right
from collections import namedtuple
from datetime import date, timedelta

ORG = "NextCommunity"
API_URL = "https://api.github.com"
README_PATH = os.path.join(os.path.dirname(__file__), "..", "profile", "README.md")
LEADERBOARD_START = "<!-- LEADERBOARD:START -->"
LEADERBOARD_END = "<!-- LEADERBOARD:END -->"
SPONSORS_START = "<!-- SPONSORS:START -->"
SPONSORS_END = "<!-- SPONSORS:END -->"

# Maximum number of sponsor buttons to show in the showcase section.
MAX_SPONSOR_BUTTONS = 5
SITE_REPO_NAME = "NextCommunity.github.io"
DOTGITHUB_REPO_NAME = ".github"

# Self-documenting record for each commit entry collected across all repos.
CommitRecord = namedtuple(
    "CommitRecord",
    ["login", "email", "is_bot", "repo_name", "commit_date", "is_coauthor"],
)

# URL for the canonical level definitions shared with the website.
LEVELS_JSON_URL = (
    "https://raw.githubusercontent.com/NextCommunity/"
    "NextCommunity.github.io/main/src/_data/levels.json"
)

# Manual email-to-login mapping for contributors who commit with multiple
# email addresses that may not all be linked to their GitHub account.
# Add entries like: "alternate@example.com": "github_login"
EMAIL_ALIASES = {}

# --- Gamification: Rarity visual indicators ---
RARITY_INDICATORS = {
    "common": "⬜",
    "uncommon": "🟩",
    "rare": "🟦",
    "epic": "🟪",
    "legendary": "🟧",
    "mythic": "🟥",
    "absolute": "⬛",
}

# Rarity ordering from lowest to highest, derived from the canonical
# indicator mapping to avoid duplicated rarity definitions.
RARITY_ORDER = list(RARITY_INDICATORS)
_RARITY_RANK = {r: i for i, r in enumerate(RARITY_ORDER)}

# Milestones used for the progress bar.  The bar shows how far along a
# contributor is to the *next* milestone.
MILESTONES = [
    10, 20, 30, 40, 50, 60, 70, 80, 90, 100,
    150, 200, 250, 300, 400, 500, 750, 1000,
]

# Curated level samples shown in the Gamification Guide table.
SAMPLE_LEVELS = [0, 1, 5, 10, 25, 50, 100, 200, 250, 500, 750, 1000]

# --- Gamification: Points configuration ---
# Points are a composite score rewarding commits, streaks, achievements,
# multi-repo contributions, and rarity progression.
POINTS_CONFIG = {
    "per_commit": 10,
    "per_streak_day": 5,
    "per_achievement": 15,
    "per_extra_repo": 20,   # bonus per repo beyond the first
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

# Minimal built-in fallback levels used when the remote JSON cannot be
# fetched.  Each entry matches the levels.json schema.
FALLBACK_LEVELS = [
    {"level": 0, "name": "Newbie", "emoji": "🐣", "color": "#94a3b8",
     "rarity": "common", "description": "Hello World."},
    {"level": 1, "name": "Script Kid", "emoji": "🛹", "color": "#10b981",
     "rarity": "common", "description": "Copy-paste from Stack Overflow."},
    {"level": 5, "name": "Data Miner", "emoji": "💎", "color": "#06b6d4",
     "rarity": "uncommon", "description": "Sifting through JSON for gold."},
    {"level": 10, "name": "Architect", "emoji": "👑", "color": "#ef4444",
     "rarity": "epic", "description": "You dream in UML diagrams."},
    {"level": 25, "name": "Kingslayer", "emoji": "🗡️", "color": "#facc15",
     "rarity": "epic", "description": "There are no men like me."},
    {"level": 50, "name": "Ring-bearer", "emoji": "💍", "color": "#fbbf24",
     "rarity": "legendary", "description": "Carry it to the fire."},
    {"level": 100, "name": "Eru Ilúvatar", "emoji": "✨", "color": "#fbbf24",
     "rarity": "mythic", "description": "The Creator."},
    {"level": 200, "name": "One With The Force", "emoji": "🌌",
     "color": "#6366f1", "rarity": "mythic",
     "description": "Luminous beings are we."},
    {"level": 250, "name": "The Source", "emoji": "🔆",
     "color": "#ffffff", "rarity": "mythic",
     "description": "Where the path ends and the cycle restarts."},
    {"level": 500, "name": "The Creative Director", "emoji": "✨",
     "color": "#ffffff", "rarity": "mythic",
     "description": "The vision is complete. Roll credits."},
    {"level": 750, "name": "Meta-Reality Architect", "emoji": "🏛️",
     "color": "#fbbf24", "rarity": "mythic",
     "description": "You designed the cage you live in. It's quite nice."},
    {"level": 1000, "name": "Infinity", "emoji": "♾️", "color": "#000000",
     "rarity": "absolute", "description": "Beyond all limits."},
]

# --- Gamification: Achievement definitions ---
# Each entry is (emoji, label, description, check_function).  The check
# function receives a contributor dict with keys: commits, repos_count,
# longest_streak, level_rarity, peak_rarity.


def _peak_rarity_rank(contrib):
    """Return the numeric rank for a contributor's peak rarity."""
    return _RARITY_RANK.get(
        contrib.get("peak_rarity", contrib.get("level_rarity")), 0,
    )


ACHIEVEMENTS = [
    ("🎯", "First Commit", "Make your first contribution",
     lambda c: c["commits"] >= 1),
    ("✋", "High Five", "Reach 5 commits",
     lambda c: c["commits"] >= 5),
    ("🌟", "Rising Star", "Reach 25 commits",
     lambda c: c["commits"] >= 25),
    ("🌐", "Explorer", "Contribute to 2+ repositories",
     lambda c: c["repos_count"] >= 2),
    ("🏗️", "Architect", "Contribute to 3+ repositories",
     lambda c: c["repos_count"] >= 3),
    ("💪", "Dedicated", "Reach 50 commits",
     lambda c: c["commits"] >= 50),
    ("🚀", "Rockstar", "Reach 100 commits",
     lambda c: c["commits"] >= 100),
    ("🛡️", "Quarter Master", "Reach 250 commits",
     lambda c: c["commits"] >= 250),
    ("⭐", "Superstar", "Reach 500 commits",
     lambda c: c["commits"] >= 500),
    ("👑", "Elite", "Reach 750 commits",
     lambda c: c["commits"] >= 750),
    ("🏆", "Thousand Club", "Reach 1000 commits",
     lambda c: c["commits"] >= 1000),
    ("🌱", "Quick Streak", "Commit for 3+ consecutive days",
     lambda c: c["longest_streak"] >= 3),
    ("📆", "Weekday Warrior", "Commit for 5+ consecutive days",
     lambda c: c["longest_streak"] >= 5),
    ("📅", "Week Streak", "Commit for 7+ consecutive days",
     lambda c: c["longest_streak"] >= 7),
    ("💫", "Fortnight Streak", "Commit for 14+ consecutive days",
     lambda c: c["longest_streak"] >= 14),
    ("🗓️", "Three-Week Streak", "Commit for 21+ consecutive days",
     lambda c: c["longest_streak"] >= 21),
    ("🔥", "Month Streak", "Commit for 30+ consecutive days",
     lambda c: c["longest_streak"] >= 30),
    ("⬜", "Common Ground", "Reach a common-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["common"]),
    ("🟩", "Uncommon Rising", "Reach an uncommon-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["uncommon"]),
    ("🟦", "Rare Find", "Reach a rare-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["rare"]),
    ("🟪", "Epic Coder", "Reach an epic-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["epic"]),
    ("🟧", "Legendary Dev", "Reach a legendary-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["legendary"]),
    ("🟥", "Mythic Status", "Reach a mythic-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["mythic"]),
    ("⬛", "Absolute Power", "Reach an absolute-rarity level",
     lambda c: _peak_rarity_rank(c) >= _RARITY_RANK["absolute"]),
]


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


def fetch_levels_json():
    """Fetch the canonical level definitions from the website repository.

    Returns a list of level dicts sorted by level number.  Falls back to
    :data:`FALLBACK_LEVELS` on any network or parsing error.
    """
    try:
        req = urllib.request.Request(
            LEVELS_JSON_URL,
            headers={"User-Agent": "NextCommunity-Leaderboard-Script"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list) and data:
            data.sort(key=lambda d: d.get("level", 0))
            return data
        print("Warning: levels.json returned empty or invalid data, using fallback")
    except urllib.error.URLError as exc:
        print(f"Warning: Network error fetching levels.json, using fallback: {exc}")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: Failed to parse levels.json, using fallback: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: Unexpected error fetching levels.json, using fallback: {exc}")
    return list(FALLBACK_LEVELS)


# Default level entry used as ultimate fallback.
_DEFAULT_LEVEL = {
    "level": 0, "name": "Newbie", "emoji": "🐣",
    "rarity": "common", "description": "", "color": "#94a3b8",
}


def _build_levels_lookup(levels_data):
    """Return a dict mapping level number → level dict for fast lookup."""
    return {entry["level"]: entry for entry in levels_data}


def _sorted_level_keys(levels_lookup):
    """Return sorted level keys for bisect-based lookups."""
    return sorted(levels_lookup)


def compute_level(commits, levels_lookup, _sorted_keys=None):
    """Return a level-info dict for a commit count using *levels_lookup*.

    Uses bisect for O(log n) lookup.  The level number is the highest
    defined level ≤ *commits*.  The returned dict has keys: ``level``,
    ``name``, ``emoji``, ``rarity``, ``description``, ``color``.
    """
    if not levels_lookup:
        return dict(_DEFAULT_LEVEL)

    if _sorted_keys is None:
        _sorted_keys = _sorted_level_keys(levels_lookup)

    idx = bisect_right(_sorted_keys, commits) - 1
    if idx < 0:
        idx = 0
    level_num = _sorted_keys[idx]
    return dict(levels_lookup.get(level_num, _DEFAULT_LEVEL))


def compute_peak_rarity(commits, levels_lookup, _sorted_keys=None):
    """Return the highest rarity achieved for defined levels up to *commits*.

    This scans the defined level entries in *levels_lookup* whose level keys
    are less than or equal to *commits*, then returns the rarity string with
    the highest rank among those entries.

    *_sorted_keys* is an optional pre-computed sorted list of level keys
    (from :func:`_sorted_level_keys`).  When provided it avoids redundant
    sorting across repeated calls.
    """
    if not levels_lookup:
        return _DEFAULT_LEVEL.get("rarity", "common")

    if _sorted_keys is None:
        _sorted_keys = _sorted_level_keys(levels_lookup)

    best_rarity = "common"
    best_rank = _RARITY_RANK["common"]
    for key in _sorted_keys:
        if key > commits:
            break
        entry_rarity = levels_lookup[key].get("rarity", "common")
        entry_rank = _RARITY_RANK.get(entry_rarity, 0)
        if entry_rank > best_rank:
            best_rarity = entry_rarity
            best_rank = entry_rank
    return best_rarity


def compute_longest_streak(commit_dates):
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


def compute_current_streak(commit_dates, today=None):
    """Return the current active consecutive-day streak ending today or yesterday.

    If the contributor committed today, the streak counts backwards from today.
    If they last committed yesterday, the streak counts backwards from
    yesterday.  Otherwise the current streak is 0.
    """
    if not commit_dates:
        return 0
    if today is None:
        today = date.today()
    dates_set = commit_dates
    # The streak must touch today or yesterday to be "active"
    if today in dates_set:
        start = today
    elif (today - timedelta(days=1)) in dates_set:
        start = today - timedelta(days=1)
    else:
        return 0
    streak = 0
    day = start
    while day in dates_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


def get_achievements(contributor):
    """Return a list of ``(emoji, label)`` tuples the contributor has earned."""
    return [
        (emoji, label)
        for emoji, label, _desc, check in ACHIEVEMENTS
        if check(contributor)
    ]


def next_milestone(commits):
    """Return the next milestone target above *commits*, or ``None`` at max."""
    for m in MILESTONES:
        if commits < m:
            return m
    return None


def prev_milestone(commits):
    """Return the last milestone at or below *commits*, or 0."""
    prev = 0
    for m in MILESTONES:
        if m <= commits:
            prev = m
        else:
            break
    return prev


def progress_bar(commits, width=8):
    """Return a text progress bar toward the next milestone.

    The bar fills relative to the range between the previous and next
    milestones so that reaching a milestone resets the bar.
    """
    target = next_milestone(commits)
    if target is None:
        return "MAX ✨"
    base = prev_milestone(commits)
    span = target - base
    if span <= 0:
        return "MAX ✨"
    progress = commits - base
    filled = min((width * progress) // span, width)
    empty = width - filled
    pct = min((100 * progress) // span, 100)
    return f"`[{'█' * filled}{'░' * empty}]` {pct}% → {target}"


def compute_points(contributor):
    """Return a gamified point total for a contributor.

    Points reward multiple dimensions of participation:
    - Commits (base contribution)
    - Longest streak (consistency)
    - Achievements earned (milestones)
    - Multi-repo contributions (breadth)
    - Rarity tier reached (progression)
    """
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

    # Collect CommitRecord entries for every commit across all repos.
    # Co-authors extracted from commit messages are added as separate
    # entries with login=None and is_coauthor=True so they go through
    # email→login resolution.
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

                # Extract commit date for streak tracking
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

                # Credit co-authors from Co-authored-by trailers
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
        except urllib.error.URLError as exc:
            print(f"Warning: Failed to fetch commits for {repo_name}: {exc}")
            had_errors = True

    # --- Phase 1: build email → login mapping ---
    email_to_login = dict(EMAIL_ALIASES)

    for rec in all_commits:
        if not rec.email:
            continue
        if rec.login and rec.email not in email_to_login:
            email_to_login[rec.email] = rec.login
        elif rec.login and rec.email in email_to_login and email_to_login[rec.email] != rec.login:
            print(
                f"Warning: email {rec.email} maps to both "
                f"{email_to_login[rec.email]} and {rec.login}; keeping first"
            )
        elif not rec.login and rec.email not in email_to_login:
            resolved = resolve_login_from_noreply(rec.email)
            if resolved:
                email_to_login[rec.email] = resolved

    # --- Phase 2: count commits per resolved identity ---
    contributors = {}
    for rec in all_commits:
        if rec.is_bot:
            continue

        resolved = rec.login or email_to_login.get(rec.email)
        if not resolved:
            continue

        # Skip bots: logins ending with [bot], logins identified as bots
        # from API metadata, or emails belonging to known bot accounts.
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
    levels_data = fetch_levels_json()
    levels_lookup = _build_levels_lookup(levels_data)
    sorted_keys = _sorted_level_keys(levels_lookup)

    # Compute gamification stats for each contributor
    today = date.today()
    for contrib in contributors.values():
        contrib["repos_count"] = len(contrib["repos"])
        commit_dates = contrib["commit_dates"]
        contrib["longest_streak"] = compute_longest_streak(commit_dates)
        contrib["current_streak"] = compute_current_streak(
            commit_dates, today=today,
        )
        contrib["days_active"] = len(commit_dates)
        if commit_dates:
            contrib["first_commit_date"] = min(commit_dates).isoformat()
            contrib["last_commit_date"] = max(commit_dates).isoformat()
        else:
            contrib["first_commit_date"] = "—"
            contrib["last_commit_date"] = "—"
        level_info = compute_level(
            contrib["commits"], levels_lookup, _sorted_keys=sorted_keys,
        )
        contrib["level_num"] = level_info.get("level", 0)
        contrib["level_emoji"] = level_info.get("emoji", "🐣")
        contrib["level_title"] = level_info.get("name", "Newbie")
        contrib["level_rarity"] = level_info.get("rarity", "common")
        contrib["level_description"] = level_info.get("description", "")
        contrib["level_color"] = level_info.get("color", "#94a3b8")
        contrib["peak_rarity"] = compute_peak_rarity(
            contrib["commits"], levels_lookup, _sorted_keys=sorted_keys,
        )
        contrib["achievements"] = get_achievements(contrib)
        contrib["points"] = compute_points(contrib)
        # Clean up non-serializable fields
        del contrib["repos"]
        del contrib["commit_dates"]

    sorted_contributors = sorted(
        contributors.values(), key=lambda c: c["commits"], reverse=True
    )
    return sorted_contributors, had_errors, levels_data


# --- Sponsor button generation ---

# Rotating color pairs (badge_color, label_color) used for the shields.io
# sponsor buttons so each contributor gets a distinct look.
_SPONSOR_COLORS = [
    ("ff6b6b", "feca57"),
    ("ff9ff3", "48dbfb"),
    ("54a0ff", "5f27cd"),
    ("ee5a24", "10ac84"),
    ("0abde3", "f368e0"),
    ("6c5ce7", "fdcb6e"),
    ("e17055", "00b894"),
    ("fd79a8", "636e72"),
]


def _badge_escape(text):
    """Escape characters that are special in shields.io badge URLs.

    Shields.io uses ``-`` as a separator and ``_`` as a space.  Literal
    hyphens must be doubled and underscores escaped.
    """
    return text.replace("-", "--").replace("_", "__")


def has_sponsors_page(login, token=None):
    """Check whether *login* has an active GitHub Sponsors page.

    Uses the ``GET /users/{login}`` endpoint and inspects the
    ``has_sponsors_listing`` field added by the GitHub REST API (v2022-11-28).
    Returns ``True`` if the user is sponsorable, ``False`` otherwise (including
    on network/API errors so that a single failure doesn't block the whole
    sponsors section).
    """
    url = f"{API_URL}/users/{login}"
    try:
        data = gh_request(url, token)
        if isinstance(data, dict):
            return bool(data.get("has_sponsors_listing", False))
    except urllib.error.URLError:
        pass
    return False


def generate_sponsors_html(contributors, token=None):
    """Generate the HTML for the sponsors showcase buttons.

    Iterates through the ranked contributor list and checks each one for an
    active GitHub Sponsors page.  Up to :data:`MAX_SPONSOR_BUTTONS`
    sponsorable contributors are included.  Contributors without a sponsors
    page are silently skipped.

    Returns the inner HTML (without the surrounding markers).
    """
    rank_badges = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [
        '  <p>',
        '    <strong>🏆 Featured Leaderboard Sponsors Showcase 🏆</strong><br>',
        '    <sub>The first {n} contributors on our leaderboard who have '
        '<a href="https://github.com/sponsors">GitHub Sponsors</a> profiles '
        'get showcased here — climb the ranks, enable Sponsors, and get '
        'featured!</sub>'.format(n=MAX_SPONSOR_BUTTONS),
        '  </p>',
        '  <p>',
    ]

    shown = 0
    for rank, contrib in enumerate(contributors, start=1):
        if shown >= MAX_SPONSOR_BUTTONS:
            break
        login = contrib["login"]
        if not has_sponsors_page(login, token):
            print(f"  Skipping {login} (rank {rank}): no GitHub Sponsors page")
            continue
        print(f"  Including {login} (rank {rank}): has GitHub Sponsors page")
        badge_color, label_color = _SPONSOR_COLORS[
            shown % len(_SPONSOR_COLORS)
        ]
        rank_label = rank_badges.get(rank, "🏅")
        escaped = _badge_escape(login)
        badge_url = (
            f"https://img.shields.io/badge/"
            f"💖_Sponsor_{escaped}-{rank_label}_Rank_{rank}-"
            f"{badge_color}?style=for-the-badge&labelColor={label_color}"
        )
        link = f"https://github.com/sponsors/{login}"
        sep = "" if shown == MAX_SPONSOR_BUTTONS - 1 else "<br>"
        lines.append(
            f'    <a href="{link}">\n'
            f'      <img src="{badge_url}" alt="Sponsor {login}"></a>{sep}'
        )
        shown += 1

    lines.append('  </p>')
    return "\n".join(lines)


def generate_markdown(contributors, levels_data):
    """Generate a gamified markdown leaderboard from contributor data."""
    rank_badges = {1: "🥇", 2: "🥈", 3: "🥉"}
    total = len(contributors)

    lines = [
        "",
        '<div align="center">',
        "",
        "## 🏆 Organization Leaderboard",
        "",
        "| Rank | Contributor | Level | Rarity | Commits | Progress | Streak | Badges | Points |",
        "|------|-------------|:-----:|:------:|:-------:|----------|:------:|--------|-------:|",
    ]
    for i, contrib in enumerate(contributors, start=1):
        login = contrib["login"]
        commits = contrib["commits"]
        authored = contrib["authored_commits"]
        coauthored = contrib["coauthored_commits"]
        level_num = contrib["level_num"]
        level_emoji = contrib["level_emoji"]
        level_title = contrib["level_title"]
        level_rarity = contrib["level_rarity"]
        longest_streak = contrib["longest_streak"]
        current_streak = contrib["current_streak"]
        achievements = contrib["achievements"]
        points = contrib["points"]
        repos_count = contrib["repos_count"]

        badge = rank_badges.get(i, "")
        rank = f"{i} {badge}" if badge else str(i)
        level = f"{level_emoji} Lv.{level_num} {level_title}"
        rarity_indicator = RARITY_INDICATORS.get(level_rarity, "⬜")
        rarity_display = f"{rarity_indicator} {level_rarity}"
        prog = progress_bar(commits)

        # Streak: show current/longest when they differ
        if current_streak > 0 and current_streak != longest_streak:
            streak_display = f"⚡ {current_streak}d / 🏆 {longest_streak}d"
        elif longest_streak > 0:
            streak_display = f"⚡ {longest_streak}d"
        else:
            streak_display = "—"

        # Badges with achievement count
        ach_count = len(achievements)
        badges_emojis = " ".join(emoji for emoji, _label in achievements)
        if ach_count > 0:
            badges = f"🏅×{ach_count} {badges_emojis}"
        else:
            badges = "—"

        points_display = f"{points:,}"

        # Commits with repo count annotation
        commits_display = f"✏️ {authored}"
        if coauthored > 0:
            commits_display += f" · 🤝 {coauthored}"
        commits_display += f" · 📦 {repos_count}"

        lines.append(
            f"| {rank} | [@{login}](https://github.com/{login})"
            f" | {level} | {rarity_display} | {commits_display}"
            f" | {prog} | {streak_display}"
            f" | {badges} | {points_display} |"
        )

    lines.append("")
    lines.append("</div>")
    lines.append("")

    # --- Extended Statistics table ---
    lines.append("<details>")
    lines.append('<summary><strong>📊 Extended Statistics</strong></summary>')
    lines.append("")
    lines.append(
        "| Rank | Contributor | First Commit | Last Active"
        " | Days Active | Commits/Day | Repo Breakdown | Percentile |"
    )
    lines.append(
        "|------|-------------|:------------:|:-----------:"
        "|:-----------:|:-----------:|----------------|:----------:|"
    )
    for i, contrib in enumerate(contributors, start=1):
        login = contrib["login"]
        first_date = contrib["first_commit_date"]
        last_date = contrib["last_commit_date"]
        days_active = contrib["days_active"]
        commits = contrib["commits"]
        cpd = f"{commits / days_active:.1f}" if days_active > 0 else "—"
        pctile = max(1, round(100 * i / total)) if total > 0 else 100

        # Repo breakdown
        breakdown_parts = []
        site_c = contrib["site_commits"]
        dg_c = contrib["dotgithub_commits"]
        other_c = commits - site_c - dg_c
        if site_c > 0:
            breakdown_parts.append(f"🌐 {site_c}")
        if dg_c > 0:
            breakdown_parts.append(f"⚙️ {dg_c}")
        if other_c > 0:
            breakdown_parts.append(f"📁 {other_c}")
        breakdown = " · ".join(breakdown_parts) if breakdown_parts else "—"

        lines.append(
            f"| {i} | [@{login}](https://github.com/{login})"
            f" | {first_date} | {last_date}"
            f" | {days_active} | {cpd}"
            f" | {breakdown} | Top {pctile}% |"
        )
    lines.append("")
    lines.append(
        "> 🌐 = site commits · ⚙️ = .github commits · 📁 = other repos"
    )
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("<details>")
    lines.append('<summary><strong>🎮 Gamification Guide</strong></summary>')
    lines.append("")
    lines.append("#### Level System")
    lines.append("")
    lines.append(
        "Each commit levels you up through themed sagas — from tech "
        "to fantasy to sci-fi. Levels are pulled from the "
        "[community site](https://nextcommunity.github.io/) and cap "
        "at the maximum defined level."
    )
    lines.append("")
    lines.append("| Commits | Level | Rarity |")
    lines.append("|:-------:|-------|:------:|")
    # Show a curated sample of notable milestone levels
    levels_lookup = _build_levels_lookup(levels_data)
    for lvl_num in SAMPLE_LEVELS:
        if lvl_num in levels_lookup:
            entry = levels_lookup[lvl_num]
            ri = RARITY_INDICATORS.get(entry.get("rarity", "common"), "⬜")
            lines.append(
                f"| {lvl_num} | {entry['emoji']} {entry['name']}"
                f" | {ri} {entry.get('rarity', '')} |"
            )
    lines.append("")
    unique_levels = len(levels_lookup)
    lines.append(f"> There are **{unique_levels}** unique levels to discover!")
    lines.append("")
    lines.append("#### Rarity Tiers")
    lines.append("")
    lines.append("| Indicator | Rarity |")
    lines.append("|:---------:|--------|")
    for rarity, indicator in RARITY_INDICATORS.items():
        lines.append(f"| {indicator} | {rarity.title()} |")
    lines.append("")
    lines.append("#### Milestones")
    lines.append("")
    lines.append(
        "The progress bar tracks your advancement toward the next "
        "milestone: **"
        + ", ".join(str(m) for m in MILESTONES)
        + "** commits."
    )
    lines.append("")
    lines.append("#### Achievements")
    lines.append("")
    lines.append("| Badge | Achievement | How to Earn |")
    lines.append("|:-----:|-------------|-------------|")
    for emoji, label, desc, _check in ACHIEVEMENTS:
        lines.append(f"| {emoji} | {label} | {desc} |")
    lines.append("")
    lines.append("#### Points System")
    lines.append("")
    lines.append(
        "Points are a composite score rewarding multiple dimensions "
        "of participation:"
    )
    lines.append("")
    cfg = POINTS_CONFIG
    lines.append("| Activity | Points |")
    lines.append("|----------|-------:|")
    lines.append(f"| Each commit | +{cfg['per_commit']} |")
    lines.append(f"| Each streak day | +{cfg['per_streak_day']} |")
    lines.append(f"| Each achievement earned | +{cfg['per_achievement']} |")
    lines.append(f"| Each extra repo (beyond first) | +{cfg['per_extra_repo']} |")
    for rarity, bonus in cfg["rarity_bonus"].items():
        if bonus > 0:
            ri = RARITY_INDICATORS.get(rarity, "")
            lines.append(f"| {ri} {rarity.title()} rarity bonus | +{bonus} |")
    lines.append("")
    lines.append("#### Extended Statistics")
    lines.append("")
    lines.append(
        "The **📊 Extended Statistics** section (above) provides "
        "additional per-contributor metrics:"
    )
    lines.append("")
    lines.append("| Stat | Description |")
    lines.append("|------|-------------|")
    lines.append("| First Commit | Date of the contributor's earliest commit |")
    lines.append("| Last Active | Date of the contributor's most recent commit |")
    lines.append("| Days Active | Total unique days with at least one commit |")
    lines.append(
        "| Commits/Day | Average total commits (authored + co-authored) "
        "per active day |"
    )
    lines.append(
        "| Repo Breakdown | Commits split by repository: "
        "🌐 site · ⚙️ .github · 📁 other |"
    )
    lines.append("| Percentile | Contributor's ranking position as a percentile |")
    lines.append("")
    lines.append(
        "The main table also shows: **📦** repo count in the Commits "
        "column, **⚡/🏆** current vs longest streak, and **🏅×N** "
        "achievement count alongside badges."
    )
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _replace_section(content, start_marker, end_marker, new_inner):
    """Replace content between *start_marker* and *end_marker*.

    Returns the updated string.  If both markers are missing the section is
    appended.  If only one marker is present an error is printed and *None*
    is returned.
    """
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker, start_idx) if start_idx != -1 else -1
    if start_idx != -1 and end_idx != -1:
        before = content[:start_idx]
        after = content[end_idx + len(end_marker):]
        return (
            f"{before}{start_marker}\n"
            f"{new_inner}\n"
            f"{end_marker}{after}"
        )
    if start_idx == -1 and end_idx == -1:
        return (
            f"{content.rstrip()}\n\n"
            f"{start_marker}\n"
            f"{new_inner}\n"
            f"{end_marker}\n"
        )
    print(
        f"Error: Mismatched markers ({start_marker} / {end_marker}) in {README_PATH}",
        file=sys.stderr,
    )
    return None


def update_readme(leaderboard_md, sponsors_html=None):
    """Update the profile README with the leaderboard and sponsors content."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Update sponsors section first (appears earlier in the file).
    if sponsors_html is not None:
        result = _replace_section(content, SPONSORS_START, SPONSORS_END, sponsors_html)
        if result is None:
            return
        content = result

    # Update leaderboard section.
    result = _replace_section(content, LEADERBOARD_START, LEADERBOARD_END, leaderboard_md)
    if result is None:
        return
    content = result

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated {README_PATH}")


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set. API rate limits will be very low.")

    try:
        contributors, had_errors, levels_data = build_leaderboard(token)
    except urllib.error.URLError as exc:
        print(f"Error: API failure while fetching data: {exc}", file=sys.stderr)
        sys.exit(1)

    if not contributors:
        if had_errors:
            print("Error: No contributors found due to API failures.", file=sys.stderr)
            sys.exit(1)
        print("No contributors found. The organization may have no public repos or contributors.")
        sys.exit(0)

    leaderboard_md = generate_markdown(contributors, levels_data)
    print("Checking GitHub Sponsors status for top contributors...")
    sponsors_html = generate_sponsors_html(contributors, token=token)
    update_readme(leaderboard_md, sponsors_html=sponsors_html)
    print(f"Leaderboard updated with {len(contributors)} contributors.")


if __name__ == "__main__":
    main()
