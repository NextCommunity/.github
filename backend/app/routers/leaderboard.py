"""Leaderboard API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.models.contributor import AchievementBadge, ContributorSummary
from backend.app.models.leaderboard import (
    LeaderboardResponse,
    RefreshResponse,
)
from backend.app.services.cache import cache
from backend.app.services.leaderboard import build_leaderboard
from backend.app.services.levels import progress_bar

router = APIRouter(prefix="/api", tags=["leaderboard"])

CACHE_KEY = "leaderboard"


async def _get_cached_leaderboard() -> tuple[list[dict], bool, list[dict]]:
    """Return cached leaderboard data, rebuilding if stale."""
    cached = await cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    result = await build_leaderboard()
    await cache.set(CACHE_KEY, result)
    return result


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    summary="Get the full leaderboard",
    description="Returns all contributors ranked by commit count with gamification data.",
)
async def get_leaderboard() -> LeaderboardResponse:
    contributors, had_errors, _levels = await _get_cached_leaderboard()
    summaries = [
        ContributorSummary(
            rank=i,
            login=c["login"],
            commits=c["commits"],
            authored_commits=c["authored_commits"],
            coauthored_commits=c["coauthored_commits"],
            level_num=c["level_num"],
            level_emoji=c["level_emoji"],
            level_title=c["level_title"],
            level_rarity=c["level_rarity"],
            peak_rarity=c["peak_rarity"],
            longest_streak=c["longest_streak"],
            repos_count=c["repos_count"],
            achievement_count=len(c["achievements"]),
            points=c["points"],
        )
        for i, c in enumerate(contributors, start=1)
    ]
    return LeaderboardResponse(
        total_contributors=len(contributors),
        had_errors=had_errors,
        contributors=summaries,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh leaderboard data",
    description="Force re-fetch from GitHub API and rebuild the leaderboard cache.",
)
async def refresh_leaderboard() -> RefreshResponse:
    await cache.invalidate(CACHE_KEY)
    contributors, had_errors, _levels = await _get_cached_leaderboard()
    msg = "Leaderboard refreshed successfully"
    if had_errors:
        msg += " (some repos had API errors)"
    return RefreshResponse(
        status="ok",
        contributors_count=len(contributors),
        message=msg,
    )
