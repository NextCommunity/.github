"""Level computation service.

Mirrors the level system from ``scripts/leaderboard.py`` using the same
canonical level definitions and bisect-based lookup.
"""

from __future__ import annotations

import json

import httpx

from backend.app.config import settings

# --- Rarity visual indicators ---
RARITY_INDICATORS: dict[str, str] = {
    "common": "⬜",
    "uncommon": "🟩",
    "rare": "🟦",
    "epic": "🟪",
    "legendary": "🟧",
    "mythic": "🟥",
    "absolute": "⬛",
}

RARITY_ORDER: list[str] = list(RARITY_INDICATORS)
RARITY_RANK: dict[str, int] = {r: i for i, r in enumerate(RARITY_ORDER)}

# Milestones used for the progress bar.
MILESTONES: list[int] = [
    10, 20, 30, 40, 50, 60, 70, 80, 90, 100,
    150, 200, 250, 300, 400, 500, 750, 1000,
]

# Curated level samples shown in guides.
SAMPLE_LEVELS: list[int] = [0, 1, 5, 10, 25, 50, 100, 200, 250, 500, 750, 1000]

# Minimal built-in fallback levels.
FALLBACK_LEVELS: list[dict] = [
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

_DEFAULT_LEVEL: dict = {
    "level": 0, "name": "Newbie", "emoji": "🐣",
    "rarity": "common", "description": "", "color": "#94a3b8",
}


async def fetch_levels_json() -> list[dict]:
    """Fetch canonical level definitions from the website repository."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                settings.levels_json_url,
                headers={"User-Agent": "NextCommunity-Leaderboard-Backend"},
            )
            resp.raise_for_status()
            data = json.loads(resp.text)
        if isinstance(data, list) and data:
            data.sort(key=lambda d: d.get("level", 0))
            return data
    except Exception:
        pass
    return list(FALLBACK_LEVELS)


def build_levels_lookup(levels_data: list[dict]) -> dict[int, dict]:
    """Return a dict mapping level number → level dict."""
    return {entry["level"]: entry for entry in levels_data}


def sorted_level_keys(levels_lookup: dict[int, dict]) -> list[int]:
    """Return sorted level keys for bisect-based lookups."""
    return sorted(levels_lookup)


def compute_level(
    commits: int,
    levels_lookup: dict[int, dict],
    _sorted_keys: list[int] | None = None,
) -> dict:
    """Return a level-info dict for a commit count."""
    from bisect import bisect_right

    if not levels_lookup:
        return dict(_DEFAULT_LEVEL)

    if _sorted_keys is None:
        _sorted_keys = sorted_level_keys(levels_lookup)

    idx = bisect_right(_sorted_keys, commits) - 1
    if idx < 0:
        idx = 0
    level_num = _sorted_keys[idx]
    return dict(levels_lookup.get(level_num, _DEFAULT_LEVEL))


def compute_peak_rarity(
    commits: int,
    levels_lookup: dict[int, dict],
    _sorted_keys: list[int] | None = None,
) -> str:
    """Return the highest rarity achieved for defined levels up to *commits*."""
    if not levels_lookup:
        return _DEFAULT_LEVEL.get("rarity", "common")

    if _sorted_keys is None:
        _sorted_keys = sorted_level_keys(levels_lookup)

    best_rarity = "common"
    best_rank = RARITY_RANK["common"]
    for key in _sorted_keys:
        if key > commits:
            break
        entry_rarity = levels_lookup[key].get("rarity", "common")
        entry_rank = RARITY_RANK.get(entry_rarity, 0)
        if entry_rank > best_rank:
            best_rarity = entry_rarity
            best_rank = entry_rank
    return best_rarity


def next_milestone(commits: int) -> int | None:
    """Return the next milestone target above *commits*, or ``None`` at max."""
    for m in MILESTONES:
        if commits < m:
            return m
    return None


def prev_milestone(commits: int) -> int:
    """Return the last milestone at or below *commits*, or 0."""
    prev = 0
    for m in MILESTONES:
        if m <= commits:
            prev = m
        else:
            break
    return prev


def progress_bar(commits: int, width: int = 8) -> str:
    """Return a text progress bar toward the next milestone."""
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
    return f"[{'█' * filled}{'░' * empty}] {pct}% → {target}"
