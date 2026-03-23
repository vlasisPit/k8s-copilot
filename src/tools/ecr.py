"""ECR image inspection tool — fetches OCI labels from a private ECR image to extract git metadata.

Why this tool exists
--------------------
When a CI/CD pipeline builds a Docker image and pushes it to ECR, it can embed git metadata
(commit SHA, branch, source repo URL) directly into the image as OCI standard labels:

    org.opencontainers.image.revision  → git commit SHA
    org.opencontainers.image.ref.name  → branch name
    org.opencontainers.image.source    → GitHub repo URL

This is one-line configuration in GitHub Actions (actions/docker/build-push-action supports
it natively). When labels are present, this tool provides the full commit → branch → repo chain
automatically, with no user input required.

Current limitation
------------------
If the image was built without OCI labels (as is the case in some pipelines), this tool
falls back to checking whether the image tag itself looks like a git commit SHA — a common
CI convention (e.g., tagging images as `myrepo:a020c2d5`). In that case we can extract the
commit but not the source repo, so the agent must ask the user for the repo name.

Read-only guarantee
-------------------
This tool performs ONLY read operations against ECR:
  - boto3: ecr.get_authorization_token()  — fetches a temporary auth token, no side effects
  - HTTP GET /v2/{repo}/manifests/{ref}   — reads the image manifest
  - HTTP GET /v2/{repo}/blobs/{digest}    — reads the image config blob (contains labels)

No writes, pushes, tag mutations, or deletions are performed.
"""

import re

import boto3
import requests

# Media types for manifest list (multi-arch) vs single-arch manifest
_MANIFEST_LIST_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}

_ACCEPT_MANIFESTS = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
])


def _parse_image_ref(image_ref: str) -> tuple[str, str, str]:
    """Parse an ECR image ref into (registry, repository, reference).

    Supports:
      registry/repo@sha256:digest
      registry/repo:tag
    """
    parts = image_ref.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse image ref: {image_ref}")

    registry = parts[0]
    repo_and_ref = parts[1]

    if "@" in repo_and_ref:
        repo, reference = repo_and_ref.split("@", 1)
    elif ":" in repo_and_ref:
        repo, reference = repo_and_ref.rsplit(":", 1)
    else:
        repo, reference = repo_and_ref, "latest"

    return registry, repo, reference


def _get_ecr_token(registry: str) -> str:
    """Get a Docker-compatible Basic auth token for ECR using boto3.

    Uses ecr.get_authorization_token() — a read-only call that returns a
    temporary token valid for 12 hours. No resources are created or modified.
    """
    match = re.search(r"\.ecr\.([^.]+)\.amazonaws\.com", registry)
    if not match:
        raise ValueError(f"Cannot determine AWS region from registry: {registry}")
    region = match.group(1)

    ecr = boto3.client("ecr", region_name=region)
    resp = ecr.get_authorization_token()
    # Token is base64("AWS:<password>") — use as-is for Basic auth
    return resp["authorizationData"][0]["authorizationToken"]


def _fetch_manifest(base_url: str, reference: str, auth_header: str) -> dict:
    """Fetch a manifest via HTTP GET, following manifest lists to a single-arch manifest.

    Multi-arch images return a manifest list (index) instead of a single manifest.
    We follow it to the linux/amd64 entry (or the first entry if amd64 is not present)
    to reach the concrete manifest that contains the config blob digest.

    All requests are HTTP GET — read-only.
    """
    resp = requests.get(
        f"{base_url}/manifests/{reference}",
        headers={"Authorization": auth_header, "Accept": _ACCEPT_MANIFESTS},
        timeout=15,
    )
    resp.raise_for_status()
    manifest = resp.json()

    content_type = resp.headers.get("Content-Type", "")

    # Detect manifest list by Content-Type header or presence of a "manifests" array
    if any(t in content_type for t in _MANIFEST_LIST_TYPES) or "manifests" in manifest:
        sub_manifests = manifest.get("manifests", [])
        if not sub_manifests:
            raise ValueError("Manifest list is empty.")

        chosen = next(
            (
                m for m in sub_manifests
                if m.get("platform", {}).get("os") == "linux"
                and m.get("platform", {}).get("architecture") == "amd64"
            ),
            sub_manifests[0],
        )

        # Recurse with the platform-specific digest
        return _fetch_manifest(base_url, chosen["digest"], auth_header)

    return manifest


def _looks_like_git_sha(tag: str) -> bool:
    """Return True if the tag looks like a short or full git commit SHA."""
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", tag))


def get_image_git_info(image_ref: str) -> dict:
    """Fetch OCI labels from a private ECR image and extract git metadata.

    All ECR and registry operations are read-only (GET requests only).
    Uses the same AWS credentials already configured for EKS access.

    Returns git commit SHA, branch, and source repository URL when the image
    was built with standard OCI labels. Falls back to reading the commit SHA
    from the image tag when it looks like a git SHA (e.g. 'myrepo:a020c2d5').

    If no source repo can be determined (missing OCI labels), the agent should
    ask the user for the GitHub repo in 'owner/repo' format and then call
    get_commit_info to find the branch.

    Args:
        image_ref: Full ECR image reference, e.g.
                   '123456789.dkr.ecr.us-east-1.amazonaws.com/myrepo@sha256:abc...'
                   '123456789.dkr.ecr.us-east-1.amazonaws.com/myrepo:a020c2d5'
    """
    try:
        registry, repo, reference = _parse_image_ref(image_ref)
    except ValueError as e:
        return {"error": str(e)}

    tag_is_sha = not reference.startswith("sha256:") and _looks_like_git_sha(reference)

    try:
        token_b64 = _get_ecr_token(registry)
    except Exception as e:
        return {"error": f"Failed to get ECR auth token (check AWS credentials): {e}"}

    auth_header = f"Basic {token_b64}"
    base_url = f"https://{registry}/v2/{repo}"

    try:
        # Read-only: GET manifest
        manifest = _fetch_manifest(base_url, reference, auth_header)

        config_digest = manifest.get("config", {}).get("digest")
        if not config_digest:
            if tag_is_sha:
                return {
                    "image_ref": image_ref,
                    "git_commit": reference,
                    "no_source_repo": (
                        "No OCI labels found in manifest. "
                        f"Call find_repo_by_workflow with image_name='{repo.split('/')[-1]}' "
                        f"and ecr_registry='{registry}' to find the GitHub repo automatically."
                    ),
                }
            return {"error": "Manifest has no config blob and image tag is not a git SHA."}

        # Read-only: GET config blob (contains OCI labels)
        blob_resp = requests.get(
            f"{base_url}/blobs/{config_digest}",
            headers={"Authorization": auth_header},
            timeout=15,
        )
        blob_resp.raise_for_status()
        config = blob_resp.json()

        labels: dict = config.get("config", {}).get("Labels") or {}

        # Standard OCI label keys set by most CI systems (GitHub Actions, GitLab CI, etc.)
        git_commit = (
            labels.get("org.opencontainers.image.revision")
            or labels.get("git.commit")
            or labels.get("GIT_COMMIT")
            or (reference if tag_is_sha else None)
        )
        git_branch = (
            labels.get("org.opencontainers.image.ref.name")
            or labels.get("git.branch")
            or labels.get("GIT_BRANCH")
        )
        source_repo = (
            labels.get("org.opencontainers.image.source")
            or labels.get("git.url")
        )

        result = {"image_ref": image_ref}
        if git_commit:
            result["git_commit"] = git_commit
        if git_branch:
            result["git_branch"] = git_branch
        if source_repo:
            result["source_repo"] = source_repo
        if labels.get("org.opencontainers.image.created"):
            result["build_date"] = labels["org.opencontainers.image.created"]
        if labels.get("org.opencontainers.image.version"):
            result["version"] = labels["org.opencontainers.image.version"]
        if labels:
            result["all_labels"] = labels

        if not any(k in result for k in ("git_commit", "git_branch", "source_repo")):
            result["warning"] = (
                "Image has no OCI git labels. "
                "It was likely built without standard label support."
            )

        if tag_is_sha and "git_commit" not in result:
            result["git_commit"] = reference
            result["note"] = "Git commit SHA inferred from image tag."

        if "git_commit" in result and "source_repo" not in result:
            result["no_source_repo"] = (
                "Image has no OCI source label. "
                f"Call find_repo_by_workflow with image_name='{repo.split('/')[-1]}' "
                f"and ecr_registry='{registry}' to find the GitHub repo automatically."
            )

        return result

    except requests.HTTPError as e:
        if e.response.status_code == 401:
            return {"error": "ECR auth failed — AWS credentials may be expired."}
        if e.response.status_code == 404:
            return {"error": f"Image not found in ECR: {image_ref}"}
        return {"error": f"Registry API error: {e.response.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Failed to reach ECR registry: {e}"}
    except ValueError as e:
        return {"error": str(e)}
