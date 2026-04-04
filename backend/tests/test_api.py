"""Integration tests for API endpoints using FastAPI TestClient."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.levels import FALLBACK_LEVELS

client = TestClient(app)

# Sample contributor data for mocking
MOCK_CONTRIBUTORS = [
    {
        "login": "alice",
        "commits": 150,
        "authored_commits": 140,
        "coauthored_commits": 10,
        "site_commits": 50,
        "dotgithub_commits": 20,
        "repos_count": 3,
        "repo_names": [".github", "NextCommunity.github.io", "project-a"],
        "longest_streak": 14,
        "level_num": 100,
        "level_emoji": "✨",
        "level_title": "Eru Ilúvatar",
        "level_rarity": "mythic",
        "level_description": "The Creator.",
        "level_color": "#fbbf24",
        "peak_rarity": "mythic",
        "achievements": [("🎯", "First Commit"), ("💪", "Dedicated"), ("🚀", "Rockstar")],
        "points": 1800,
    },
    {
        "login": "bob",
        "commits": 25,
        "authored_commits": 25,
        "coauthored_commits": 0,
        "site_commits": 10,
        "dotgithub_commits": 5,
        "repos_count": 2,
        "repo_names": [".github", "NextCommunity.github.io"],
        "longest_streak": 3,
        "level_num": 25,
        "level_emoji": "🗡️",
        "level_title": "Kingslayer",
        "level_rarity": "epic",
        "level_description": "There are no men like me.",
        "level_color": "#facc15",
        "peak_rarity": "epic",
        "achievements": [("🎯", "First Commit"), ("🌟", "Rising Star")],
        "points": 400,
    },
]

MOCK_RESULT = (MOCK_CONTRIBUTORS, False, FALLBACK_LEVELS)


@pytest.fixture(autouse=True)
def mock_cache():
    """Clear cache and mock build_leaderboard for all tests."""
    with patch(
        "backend.app.routers.leaderboard.build_leaderboard",
        new_callable=AsyncMock,
        return_value=MOCK_RESULT,
    ):
        with patch(
            "backend.app.services.cache.cache.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "backend.app.services.cache.cache.set",
                new_callable=AsyncMock,
            ):
                yield


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_get_leaderboard():
    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_contributors"] == 2
    assert data["had_errors"] is False
    assert len(data["contributors"]) == 2
    assert data["contributors"][0]["login"] == "alice"
    assert data["contributors"][0]["rank"] == 1
    assert data["contributors"][1]["login"] == "bob"
    assert data["contributors"][1]["rank"] == 2


def test_get_contributor_found():
    resp = client.get("/api/contributors/alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "alice"
    assert data["commits"] == 150
    assert data["level_title"] == "Eru Ilúvatar"
    assert len(data["achievements"]) == 3
    assert data["points"] == 1800


def test_get_contributor_case_insensitive():
    resp = client.get("/api/contributors/Alice")
    assert resp.status_code == 200
    assert resp.json()["login"] == "alice"


def test_get_contributor_not_found():
    resp = client.get("/api/contributors/unknown")
    assert resp.status_code == 404


def test_get_stats():
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_contributors"] == 2
    assert data["total_commits"] == 175
    assert data["total_authored"] == 165
    assert data["total_coauthored"] == 10
    assert "rarity_distribution" in data


def test_get_levels():
    resp = client.get("/api/levels")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_levels"] == len(FALLBACK_LEVELS)
    assert len(data["levels"]) == len(FALLBACK_LEVELS)
    assert data["levels"][0]["name"] == "Newbie"


def test_get_achievements():
    resp = client.get("/api/achievements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_achievements"] == 24
    labels = [a["label"] for a in data["achievements"]]
    assert "First Commit" in labels
    assert "Thousand Club" in labels


def test_refresh_no_api_key():
    """When no API_KEY is configured, refresh should be open."""
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["contributors_count"] == 2


def test_openapi_docs():
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_timing_header():
    resp = client.get("/health")
    assert "x-process-time" in resp.headers
