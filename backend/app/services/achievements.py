"""Achievement system service.

Mirrors the achievement definitions from ``scripts/leaderboard.py``.
"""

from __future__ import annotations

from backend.app.services.levels import RARITY_RANK


def _peak_rarity_rank(contrib: dict) -> int:
    """Return the numeric rank for a contributor's peak rarity."""
    return RARITY_RANK.get(
        contrib.get("peak_rarity", contrib.get("level_rarity")), 0,
    )


# Each entry is (emoji, label, description, check_function).
ACHIEVEMENTS: list[tuple[str, str, str, object]] = [
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
    ("🏅", "Quarter Master", "Reach 250 commits",
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
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["common"]),
    ("🟩", "Uncommon Rising", "Reach an uncommon-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["uncommon"]),
    ("🟦", "Rare Find", "Reach a rare-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["rare"]),
    ("🟪", "Epic Coder", "Reach an epic-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["epic"]),
    ("🟧", "Legendary Dev", "Reach a legendary-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["legendary"]),
    ("🟥", "Mythic Status", "Reach a mythic-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["mythic"]),
    ("⬛", "Absolute Power", "Reach an absolute-rarity level",
     lambda c: _peak_rarity_rank(c) >= RARITY_RANK["absolute"]),
]


def get_achievements(contributor: dict) -> list[tuple[str, str]]:
    """Return a list of (emoji, label) tuples the contributor has earned."""
    return [
        (emoji, label)
        for emoji, label, _desc, check in ACHIEVEMENTS
        if check(contributor)
    ]
