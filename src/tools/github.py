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


def get_github_file_content(
    repo: str,
    path: str,
    search_term: str | None = None,
    ref: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    """Fetch the content of a file from a GitHub repository and return matching lines.

    Args:
        repo: Repository in 'owner/repo' format.
        path: Path to the file within the repository (e.g. 'src/server/main.py').
        search_term: Optional string to search for. Returns all matching lines with
                     5 lines of context above and below each match.
        ref: Optional branch, tag, or commit SHA. Defaults to the repo's default branch.
        start_line: Return lines from this line number (1-based, inclusive).
        end_line: Return lines up to this line number (1-based, inclusive).
                  When start_line/end_line are set, search_term is ignored.
    """
    try:
        params = {}
        if ref:
            params["ref"] = ref

        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers=_headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("encoding") != "base64":
            return {"error": f"Unexpected file encoding: {data.get('encoding')}"}

        import base64
        raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        lines = raw.splitlines()

        result = {
            "repo": repo,
            "path": path,
            "ref": ref or "default branch",
            "url": data.get("html_url"),
            "total_lines": len(lines),
        }

        # Line-range mode: return exactly the requested lines
        if start_line is not None or end_line is not None:
            lo = max(1, start_line or 1)
            hi = min(len(lines), end_line or len(lines))
            result["content"] = "\n".join(
                f"{i+1:4}: {lines[i]}" for i in range(lo - 1, hi)
            )
            result["line_range"] = f"{lo}–{hi}"
            return result

        # Search mode: return matching lines with context
        if search_term:
            matches = []
            for i, line in enumerate(lines):
                if search_term.lower() in line.lower():
                    start = max(0, i - 5)
                    end = min(len(lines), i + 6)
                    context = [
                        {"line_number": j + 1, "content": lines[j], "match": j == i}
                        for j in range(start, end)
                    ]
                    matches.append({"line_number": i + 1, "context": context})

            if matches:
                result["matches"] = matches
            else:
                result["note"] = f"'{search_term}' not found in {path}."
            return result

        # Default: return first 100 lines
        result["content"] = "\n".join(f"{i+1:4}: {l}" for i, l in enumerate(lines[:100]))
        if len(lines) > 100:
            result["truncated"] = True
            result["note"] = (
                f"File has {len(lines)} lines. "
                "Use start_line/end_line for a specific range, or search_term to find a string."
            )

        return result

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {"error": f"File '{path}' not found in {repo} (ref: {ref or 'default'})."}
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}


def search_github_code(error_message: str, repo: str) -> dict:
    """Search source code in a specific GitHub repository for an error string.

    Args:
        error_message: The error text to search for in source code.
        repo: Repository in 'owner/repo' format (required).
    """
    try:
        query = f'"{error_message}" repo:{repo}'

        resp = requests.get(
            f"{GITHUB_API}/search/code",
            headers=_headers(),
            params={"q": query, "per_page": MAX_RESULTS},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            {
                "file": item["path"],
                "url": item["html_url"],
                "repository": item["repository"]["full_name"],
            }
            for item in data.get("items", [])
        ]

        return {
            "query": error_message,
            "repo": repo,
            "results": results,
            "total_found": data.get("total_count", 0),
        }

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        if e.response.status_code == 422:
            return {"error": "Search query too long or invalid. Try a shorter error message."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}


def _check_branch(repo: str, branch: dict, full_sha: str, headers: dict) -> str | None:
    """Return the branch name if its history contains full_sha, else None."""
    # Fast path: our commit IS the branch tip
    if branch["commit"]["sha"] == full_sha:
        return branch["name"]

    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/commits",
        headers=headers,
        params={"sha": branch["name"], "per_page": 100},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    for c in resp.json():
        if c["sha"] == full_sha:
            return branch["name"]
    return None


def _branches_containing_commit(repo: str, full_sha: str, headers: dict) -> list[str]:
    """Return names of all branches whose history contains the given commit.

    GitHub's REST API has no direct "branches containing commit" endpoint
    (equivalent to `git branch --contains <sha>`). The compare API requires
    branch names on both sides and is unreliable with a commit SHA as base.

    We scan up to 100 recent commits per branch in parallel (10 workers) so
    all branches are checked concurrently instead of sequentially.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Fetch all branches (paginate to get beyond the default 30 limit)
    all_branches = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/branches",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=10,
        )
        if resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        all_branches.extend(batch)
        page += 1

    containing = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_check_branch, repo, branch, full_sha, headers): branch["name"]
            for branch in all_branches
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                containing.append(result)

    return containing


def _get_commit_details(repo: str, commit_sha: str, headers: dict) -> dict:
    """Fetch commit metadata, associated PRs, and branches containing the commit."""
    commit_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/commits/{commit_sha}",
        headers=headers,
        timeout=10,
    )
    commit_resp.raise_for_status()
    commit_data = commit_resp.json()
    full_sha = commit_data["sha"]

    commit_info = {
        "sha": full_sha,
        "message": commit_data["commit"]["message"].split("\n")[0],
        "author": commit_data["commit"]["author"]["name"],
        "date": commit_data["commit"]["author"]["date"][:10],
        "url": commit_data["html_url"],
    }

    # PRs associated with this commit — reveals the source branch even after merge
    pr_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/commits/{full_sha}/pulls",
        headers=headers,
        timeout=10,
    )
    branches_from_prs = []
    if pr_resp.status_code == 200:
        for pr in pr_resp.json():
            branches_from_prs.append({
                "branch": pr["head"]["ref"],
                "pr_number": pr["number"],
                "pr_title": pr["title"],
                "pr_state": pr["state"],
                "pr_url": pr["html_url"],
                "merged": pr.get("merged_at") is not None,
            })

    # Find all branches whose history contains this commit
    containing_branches = _branches_containing_commit(repo, full_sha, headers)

    result = {"repo": repo, "commit": commit_info}
    if containing_branches:
        result["branches_containing_commit"] = containing_branches
    if branches_from_prs:
        result["associated_prs"] = branches_from_prs
    if not containing_branches and not branches_from_prs:
        result["note"] = (
            "Commit found but not reachable from any current branch. "
            "The branch may have been deleted after merging."
        )
    return result


def find_repo_by_workflow(image_name: str, ecr_registry: str | None = None) -> dict:
    """Find the GitHub repository that contains a workflow which builds a given Docker image.

    Searches GitHub Actions workflow files (.github/workflows) for references to the
    image name and optionally the ECR registry hostname. This is used when an ECR image
    has no OCI labels — the workflow file that pushes the image is the next best source
    for finding the source repo.

    Args:
        image_name: The Docker image name to search for (e.g. 'carrara-tiledb-server').
        ecr_registry: Optional ECR registry hostname to narrow the search
                      (e.g. '980565428655.dkr.ecr.us-east-1.amazonaws.com').
    """
    try:
        # Search workflow files for the image name first — most specific signal
        query = f'"{image_name}" path:.github/workflows'
        resp = requests.get(
            f"{GITHUB_API}/search/code",
            headers=_headers(),
            params={"q": query, "per_page": MAX_RESULTS},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        # If image name alone is ambiguous, re-run with ECR registry to narrow down
        if ecr_registry and len(items) > 1:
            narrowed_resp = requests.get(
                f"{GITHUB_API}/search/code",
                headers=_headers(),
                params={
                    "q": f'"{image_name}" "{ecr_registry}" path:.github/workflows',
                    "per_page": MAX_RESULTS,
                },
                timeout=10,
            )
            if narrowed_resp.status_code == 200:
                narrowed = narrowed_resp.json().get("items", [])
                if narrowed:
                    items = narrowed

        if not items:
            return {
                "image_name": image_name,
                "repos_found": [],
                "note": (
                    f"No workflow files referencing '{image_name}' found. "
                    "The repo may be private and your GITHUB_TOKEN may not have access, "
                    "or the workflow does not reference the image name directly."
                ),
            }

        repos = []
        seen = set()
        for item in items:
            repo_name = item["repository"]["full_name"]
            if repo_name not in seen:
                seen.add(repo_name)
                repos.append({
                    "repo": repo_name,
                    "workflow_file": item["path"],
                    "url": item["html_url"],
                })

        return {
            "image_name": image_name,
            "repos_found": repos,
            "suggested_repo": repos[0]["repo"],
        }

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        if e.response.status_code == 422:
            return {"error": "Search query invalid. Try a shorter image name."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}


def get_commit_info(commit_sha: str, repo: str | None = None) -> dict:
    """Look up a specific git commit and find which branch it belongs to.

    If repo is provided, looks it up directly (works for private repos with a token).
    If repo is omitted, searches GitHub globally by commit hash (works for any repo
    accessible to your GITHUB_TOKEN).

    Args:
        commit_sha: The git commit SHA (full or short, e.g. 'a020c2d5').
        repo: Optional repository in 'owner/repo' format. If omitted, a global
              hash search is performed to discover the repo automatically.
    """
    h = _headers()
    try:
        if repo:
            return _get_commit_details(repo, commit_sha, h)

        # No repo given — search GitHub globally by commit hash
        search_resp = requests.get(
            f"{GITHUB_API}/search/commits",
            headers=h,
            params={"q": f"hash:{commit_sha}", "per_page": MAX_RESULTS},
            timeout=10,
        )
        search_resp.raise_for_status()
        items = search_resp.json().get("items", [])

        if not items:
            return {
                "error": (
                    f"Commit {commit_sha} not found via GitHub search. "
                    "The repo may be private — provide the repo name explicitly."
                )
            }

        # Use the first match to resolve the full repo, then get details
        found_repo = items[0]["repository"]["full_name"]
        full_sha = items[0]["sha"]
        result = _get_commit_details(found_repo, full_sha, h)
        result["discovered_repo"] = found_repo
        return result

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {"error": f"Commit {commit_sha} not found in repo {repo}."}
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        if e.response.status_code == 422:
            return {"error": "Commit SHA too short or invalid. Try providing more characters."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}


def search_github_commits(error_message: str, repo: str) -> dict:
    """Search commit messages in a specific GitHub repository for an error string.

    Args:
        error_message: The error text to search for in commit messages.
        repo: Repository in 'owner/repo' format (required).
    """
    try:
        query = f'"{error_message}" repo:{repo}'

        resp = requests.get(
            f"{GITHUB_API}/search/commits",
            headers=_headers(),
            params={"q": query, "per_page": MAX_RESULTS, "sort": "committer-date"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        commits = [
            {
                "sha": item["sha"][:10],
                "message": item["commit"]["message"].split("\n")[0],  # first line only
                "author": item["commit"]["author"]["name"],
                "date": item["commit"]["author"]["date"][:10],
                "url": item["html_url"],
                "branch": item.get("repository", {}).get("default_branch"),
            }
            for item in data.get("items", [])
        ]

        return {
            "query": error_message,
            "repo": repo,
            "commits": commits,
            "total_found": data.get("total_count", 0),
        }

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits."}
        if e.response.status_code == 422:
            return {"error": "Search query too long or invalid. Try a shorter error message."}
        return {"error": f"GitHub API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach GitHub API: {e}"}
