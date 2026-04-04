"""Async GitHub API client using httpx."""

from __future__ import annotations

import httpx

from backend.app.config import settings

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "NextCommunity-Leaderboard-Backend",
    "X-GitHub-Api-Version": "2022-11-28",
}

_TIMEOUT = 30.0


def _auth_headers() -> dict[str, str]:
    headers = dict(_HEADERS)
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def gh_request(url: str) -> dict | list:
    """Make an authenticated GitHub API request and return parsed JSON."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        if not resp.text.strip():
            return {}
        return resp.json()


async def get_all_pages(url: str) -> list[dict]:
    """Paginate through all results for a GitHub API endpoint."""
    results: list[dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        while True:
            separator = "&" if "?" in url else "?"
            page_url = f"{url}{separator}per_page=100&page={page}"
            resp = await client.get(page_url, headers=_auth_headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                msg = data.get("message", "Unknown error")
                raise httpx.HTTPStatusError(
                    f"Expected list from {url}, got: {msg}",
                    request=resp.request,
                    response=resp,
                )
            if not isinstance(data, list) or not data:
                break
            results.extend(data)
            if len(data) < 100:
                break
            page += 1
    return results


async def fetch_repos() -> list[dict]:
    """Fetch all public repos for the organization."""
    url = f"https://api.github.com/orgs/{settings.org_name}/repos?type=public"
    return await get_all_pages(url)


async def fetch_commits(repo_name: str) -> list[dict]:
    """Fetch all commits for a single repo."""
    url = f"https://api.github.com/repos/{settings.org_name}/{repo_name}/commits"
    return await get_all_pages(url)
