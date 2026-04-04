"""Unit tests for core leaderboard services."""

from datetime import date, timedelta

from backend.app.services.achievements import ACHIEVEMENTS, get_achievements
from backend.app.services.levels import (
    FALLBACK_LEVELS,
    MILESTONES,
    RARITY_INDICATORS,
    RARITY_ORDER,
    RARITY_RANK,
    build_levels_lookup,
    compute_level,
    compute_peak_rarity,
    next_milestone,
    prev_milestone,
    progress_bar,
    sorted_level_keys,
)
from backend.app.services.leaderboard import (
    POINTS_CONFIG,
    compute_longest_streak,
    compute_points,
    parse_co_authors,
    resolve_login_from_noreply,
)


# --- Level tests ---


def test_build_levels_lookup():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    assert 0 in lookup
    assert 1000 in lookup
    assert lookup[0]["name"] == "Newbie"


def test_sorted_level_keys():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    keys = sorted_level_keys(lookup)
    assert keys == sorted(keys)
    assert keys[0] == 0
    assert keys[-1] == 1000


def test_compute_level_zero():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    level = compute_level(0, lookup)
    assert level["level"] == 0
    assert level["name"] == "Newbie"


def test_compute_level_mid():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    level = compute_level(50, lookup)
    assert level["level"] == 50
    assert level["name"] == "Ring-bearer"


def test_compute_level_between():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    level = compute_level(7, lookup)
    assert level["level"] == 5  # Should round down to 5


def test_compute_level_max():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    level = compute_level(9999, lookup)
    assert level["level"] == 1000


def test_compute_level_empty_lookup():
    level = compute_level(50, {})
    assert level["name"] == "Newbie"


def test_compute_peak_rarity_common():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    rarity = compute_peak_rarity(0, lookup)
    assert rarity == "common"


def test_compute_peak_rarity_epic():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    rarity = compute_peak_rarity(25, lookup)
    assert rarity == "epic"


def test_compute_peak_rarity_absolute():
    lookup = build_levels_lookup(FALLBACK_LEVELS)
    rarity = compute_peak_rarity(1000, lookup)
    assert rarity == "absolute"


# --- Milestone tests ---


def test_next_milestone():
    assert next_milestone(0) == 10
    assert next_milestone(9) == 10
    assert next_milestone(10) == 20
    assert next_milestone(999) == 1000
    assert next_milestone(1000) is None


def test_prev_milestone():
    assert prev_milestone(0) == 0
    assert prev_milestone(10) == 10
    assert prev_milestone(15) == 10
    assert prev_milestone(1000) == 1000


def test_progress_bar_zero():
    bar = progress_bar(0)
    assert "0%" in bar
    assert "→ 10" in bar


def test_progress_bar_max():
    bar = progress_bar(1000)
    assert "MAX" in bar


# --- Streak tests ---


def test_longest_streak_empty():
    assert compute_longest_streak(set()) == 0


def test_longest_streak_single():
    assert compute_longest_streak({date.today()}) == 1


def test_longest_streak_consecutive():
    today = date.today()
    dates = {today - timedelta(days=i) for i in range(7)}
    assert compute_longest_streak(dates) == 7


def test_longest_streak_gap():
    today = date.today()
    dates = {today, today - timedelta(days=1), today - timedelta(days=5)}
    assert compute_longest_streak(dates) == 2


# --- Co-author tests ---


def test_parse_co_authors_basic():
    msg = "Some commit\n\nCo-authored-by: Alice <alice@example.com>"
    result = parse_co_authors(msg)
    assert result == ["alice@example.com"]


def test_parse_co_authors_multiple():
    msg = (
        "commit\n\n"
        "Co-authored-by: Alice <alice@example.com>\n"
        "Co-authored-by: Bob <bob@example.com>"
    )
    result = parse_co_authors(msg)
    assert len(result) == 2


def test_parse_co_authors_empty():
    assert parse_co_authors("") == []
    assert parse_co_authors(None) == []


# --- Noreply resolution tests ---


def test_resolve_noreply_simple():
    assert resolve_login_from_noreply(
        "alice@users.noreply.github.com"
    ) == "alice"


def test_resolve_noreply_with_id():
    assert resolve_login_from_noreply(
        "12345+alice@users.noreply.github.com"
    ) == "alice"


def test_resolve_noreply_non_noreply():
    assert resolve_login_from_noreply("alice@example.com") is None


# --- Achievement tests ---


def test_achievements_first_commit():
    contrib = {
        "commits": 1,
        "repos_count": 1,
        "longest_streak": 0,
        "level_rarity": "common",
        "peak_rarity": "common",
    }
    badges = get_achievements(contrib)
    assert any(label == "First Commit" for _, label in badges)


def test_achievements_none():
    contrib = {
        "commits": 0,
        "repos_count": 0,
        "longest_streak": 0,
        "level_rarity": "common",
        "peak_rarity": "common",
    }
    badges = get_achievements(contrib)
    # Only "Common Ground" should trigger (peak_rarity >= common is always true)
    assert len(badges) == 1
    assert badges[0][1] == "Common Ground"


# --- Points tests ---


def test_compute_points_basic():
    contrib = {
        "commits": 10,
        "longest_streak": 5,
        "achievements": [("🎯", "First Commit")],
        "repos_count": 2,
        "peak_rarity": "common",
    }
    pts = compute_points(contrib)
    expected = (
        10 * POINTS_CONFIG["per_commit"]
        + 5 * POINTS_CONFIG["per_streak_day"]
        + 1 * POINTS_CONFIG["per_achievement"]
        + 1 * POINTS_CONFIG["per_extra_repo"]
        + POINTS_CONFIG["rarity_bonus"]["common"]
    )
    assert pts == expected


# --- Data integrity tests ---


def test_rarity_order_matches_indicators():
    assert list(RARITY_INDICATORS.keys()) == RARITY_ORDER


def test_rarity_rank_values():
    for i, rarity in enumerate(RARITY_ORDER):
        assert RARITY_RANK[rarity] == i


def test_achievements_count():
    assert len(ACHIEVEMENTS) == 24


def test_milestones_sorted():
    assert MILESTONES == sorted(MILESTONES)


def test_fallback_levels_sorted():
    levels = [entry["level"] for entry in FALLBACK_LEVELS]
    assert levels == sorted(levels)
