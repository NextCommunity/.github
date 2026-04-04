"""Contributor detail API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.contributor import AchievementBadge, ContributorDetail
from backend.app.routers.leaderboard import _get_cached_leaderboard
from backend.app.services.levels import progress_bar

router = APIRouter(prefix="/api", tags=["contributors"])


@router.get(
    "/contributors/{login}",
    response_model=ContributorDetail,
    summary="Get a contributor profile",
    description="Returns full gamification data for a single contributor.",
)
async def get_contributor(login: str) -> ContributorDetail:
    contributors, _had_errors, _levels = await _get_cached_leaderboard()
    for c in contributors:
        if c["login"].lower() == login.lower():
            return ContributorDetail(
                login=c["login"],
                commits=c["commits"],
                authored_commits=c["authored_commits"],
                coauthored_commits=c["coauthored_commits"],
                site_commits=c["site_commits"],
                dotgithub_commits=c["dotgithub_commits"],
                repos_count=c["repos_count"],
                repo_names=c.get("repo_names", []),
                longest_streak=c["longest_streak"],
                level_num=c["level_num"],
                level_emoji=c["level_emoji"],
                level_title=c["level_title"],
                level_rarity=c["level_rarity"],
                level_description=c.get("level_description", ""),
                level_color=c.get("level_color", "#94a3b8"),
                peak_rarity=c["peak_rarity"],
                achievements=[
                    AchievementBadge(emoji=e, label=l)
                    for e, l in c["achievements"]
                ],
                points=c["points"],
                progress=progress_bar(c["commits"]),
            )
    raise HTTPException(status_code=404, detail=f"Contributor '{login}' not found")
