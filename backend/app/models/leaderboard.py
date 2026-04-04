"""Pydantic models for leaderboard and stats responses."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.models.contributor import ContributorSummary


class LeaderboardResponse(BaseModel):
    """Full leaderboard response."""

    total_contributors: int = Field(..., description="Total number of contributors")
    had_errors: bool = Field(..., description="Whether any API errors occurred during fetch")
    contributors: list[ContributorSummary]


class StatsResponse(BaseModel):
    """Aggregate org-wide statistics."""

    total_contributors: int
    total_commits: int
    total_authored: int
    total_coauthored: int
    total_achievements: int
    average_commits: float
    average_points: float
    top_rarity: str = Field(..., description="Highest rarity achieved across all contributors")
    rarity_distribution: dict[str, int] = Field(
        ..., description="Number of contributors at each rarity tier"
    )


class LevelEntry(BaseModel):
    """A single level definition."""

    level: int
    name: str
    emoji: str
    rarity: str = "common"
    description: str = ""
    color: str = "#94a3b8"


class LevelsResponse(BaseModel):
    """Level definitions response."""

    total_levels: int
    levels: list[LevelEntry]


class AchievementDefinition(BaseModel):
    """A single achievement definition."""

    emoji: str
    label: str
    description: str


class AchievementsResponse(BaseModel):
    """Achievement catalog response."""

    total_achievements: int
    achievements: list[AchievementDefinition]


class RefreshResponse(BaseModel):
    """Response after a cache refresh."""

    status: str = "ok"
    contributors_count: int = 0
    message: str = ""


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
