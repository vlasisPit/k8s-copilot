"""GitHub search tool — finds issues and code related to a Kubernetes error message."""

import os

import requests

GITHUB_API = "https://api.github.com"
MAX_RESULTS = 5


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def search_github(error_message: str, repo: str | None = None) -> dict:
    """Search GitHub issues and code for a given error message.

    Args:
        error_message: The error or exception text to search for.
        repo: Optional repository in 'owner/repo' format to scope the search.
    """
    try:
        query = f'"{error_message}"'
        if repo:
            query += f" repo:{repo}"

        # Search issues and PRs
        issues_resp = requests.get(
            f"{GITHUB_API}/search/issues",
            headers=_headers(),
            params={"q": query, "per_page": MAX_RESULTS, "sort": "relevance"},
            timeout=10,
        )
        issues_resp.raise_for_status()
        issues_data = issues_resp.json()

        issues = [
            {
                "title": item["title"],
                "url": item["html_url"],
                "state": item["state"],
                "repo": item["repository_url"].replace(f"{GITHUB_API}/repos/", ""),
                "comments": item["comments"],
                "created_at": item["created_at"][:10],
            }
            for item in issues_data.get("items", [])
        ]

        return {
            "query": error_message,
            "repo_filter": repo,
            "issues": issues,
            "total_found": issues_data.get("total_count", 0),
        }

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        if e.response.status_code == 422:
            return {"error": "Search query too long or invalid. Try a shorter error message."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}
