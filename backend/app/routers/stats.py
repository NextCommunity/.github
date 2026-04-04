"""Statistics and metadata API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.models.leaderboard import (
    AchievementDefinition,
    AchievementsResponse,
    LevelEntry,
    LevelsResponse,
    StatsResponse,
)
from backend.app.routers.leaderboard import _get_cached_leaderboard
from backend.app.services.achievements import ACHIEVEMENTS
from backend.app.services.levels import RARITY_ORDER, RARITY_RANK

router = APIRouter(prefix="/api", tags=["stats"])


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Aggregate organization statistics",
    description="Returns org-wide aggregate numbers: commits, contributors, achievements, rarity distribution.",
)
async def get_stats() -> StatsResponse:
    contributors, _had_errors, _levels = await _get_cached_leaderboard()

    total_commits = sum(c["commits"] for c in contributors)
    total_authored = sum(c["authored_commits"] for c in contributors)
    total_coauthored = sum(c["coauthored_commits"] for c in contributors)
    total_achievements = sum(len(c["achievements"]) for c in contributors)
    n = len(contributors) or 1

    # Rarity distribution
    rarity_dist: dict[str, int] = {r: 0 for r in RARITY_ORDER}
    top_rarity = "common"
    top_rank = 0
    for c in contributors:
        rarity = c.get("peak_rarity", "common")
        rarity_dist[rarity] = rarity_dist.get(rarity, 0) + 1
        rank = RARITY_RANK.get(rarity, 0)
        if rank > top_rank:
            top_rarity = rarity
            top_rank = rank

    return StatsResponse(
        total_contributors=len(contributors),
        total_commits=total_commits,
        total_authored=total_authored,
        total_coauthored=total_coauthored,
        total_achievements=total_achievements,
        average_commits=round(total_commits / n, 1),
        average_points=round(sum(c["points"] for c in contributors) / n, 1),
        top_rarity=top_rarity,
        rarity_distribution=rarity_dist,
    )


@router.get(
    "/levels",
    response_model=LevelsResponse,
    summary="Level definitions",
    description="Returns all level definitions with rarity tiers.",
)
async def get_levels() -> LevelsResponse:
    _contributors, _had_errors, levels_data = await _get_cached_leaderboard()
    entries = [
        LevelEntry(
            level=lv.get("level", 0),
            name=lv.get("name", ""),
            emoji=lv.get("emoji", ""),
            rarity=lv.get("rarity", "common"),
            description=lv.get("description", ""),
            color=lv.get("color", "#94a3b8"),
        )
        for lv in levels_data
    ]
    return LevelsResponse(total_levels=len(entries), levels=entries)


@router.get(
    "/achievements",
    response_model=AchievementsResponse,
    summary="Achievement catalog",
    description="Returns all possible achievements with their descriptions.",
)
async def get_achievements() -> AchievementsResponse:
    defs = [
        AchievementDefinition(emoji=emoji, label=label, description=desc)
        for emoji, label, desc, _check in ACHIEVEMENTS
    ]
    return AchievementsResponse(total_achievements=len(defs), achievements=defs)
