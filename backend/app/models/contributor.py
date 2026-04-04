"""Pydantic models for contributor data."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AchievementBadge(BaseModel):
    """A single earned achievement badge."""

    emoji: str = Field(..., description="Achievement emoji")
    label: str = Field(..., description="Achievement name")


class ContributorSummary(BaseModel):
    """Abbreviated contributor data for the leaderboard table."""

    rank: int = Field(..., description="Leaderboard rank")
    login: str = Field(..., description="GitHub login")
    commits: int = Field(..., description="Total commits")
    authored_commits: int = Field(..., description="Authored commits")
    coauthored_commits: int = Field(..., description="Co-authored commits")
    level_num: int = Field(..., description="Current level number")
    level_emoji: str = Field(..., description="Level emoji")
    level_title: str = Field(..., description="Level title")
    level_rarity: str = Field(..., description="Current level rarity tier")
    peak_rarity: str = Field(..., description="Highest rarity tier reached")
    longest_streak: int = Field(..., description="Longest commit streak in days")
    repos_count: int = Field(..., description="Number of repositories contributed to")
    achievement_count: int = Field(..., description="Number of achievements earned")
    points: int = Field(..., description="Gamified point total")


class ContributorDetail(BaseModel):
    """Full contributor profile with all gamification data."""

    login: str
    commits: int
    authored_commits: int
    coauthored_commits: int
    site_commits: int = Field(..., description="Commits to the site repo")
    dotgithub_commits: int = Field(..., description="Commits to the .github repo")
    repos_count: int
    repo_names: list[str] = Field(default_factory=list, description="Repository names")
    longest_streak: int
    level_num: int
    level_emoji: str
    level_title: str
    level_rarity: str
    level_description: str = ""
    level_color: str = "#94a3b8"
    peak_rarity: str
    achievements: list[AchievementBadge]
    points: int
    progress: str = Field("", description="Progress bar toward next milestone")
