"""
Tool definitions (JSON schema) for Claude's tool use API,
and the dispatcher that routes tool calls to their implementations.
"""

from kubernetes import client as k8s_client

from .cronjobs import get_cronjobs
from .ecr import get_image_git_info
from .deployments import get_deployment, get_deployments
from .events import get_events
from .github import find_repo_by_workflow, get_commit_info, get_github_file_content, search_github, search_github_code, search_github_commits
from .namespaces import list_namespaces
from .nodes import get_nodes
from .pods import describe_pod, get_pod_logs, get_pods

TOOLS = [
    {
        "name": "get_pods",
        "description": "List all pods in a Kubernetes namespace with their status, phase, and container states. Use this to get an overview of what's running.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace. Defaults to 'default'.",
                }
            },
        },
    },
    {
        "name": "describe_pod",
        "description": "Get detailed information about a specific pod including conditions, container statuses, restart counts, and last termination reason. Use this when a pod looks unhealthy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name."},
                "namespace": {"type": "string", "description": "Namespace. Defaults to 'default'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_pod_logs",
        "description": "Fetch logs from a pod container. Use 'previous=true' to get logs from the last terminated container (useful for crash debugging).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name."},
                "namespace": {"type": "string", "description": "Namespace. Defaults to 'default'."},
                "container": {"type": "string", "description": "Container name (optional if pod has one container)."},
                "tail_lines": {"type": "integer", "description": "Number of log lines to return. Defaults to 100."},
                "previous": {"type": "boolean", "description": "Return logs from the previous (crashed) container instance."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_events",
        "description": "Get Kubernetes events for a namespace. Optionally filter by a specific object name (pod, deployment, etc.). Warnings appear first. Very useful for diagnosing scheduling and image pull failures.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace. Defaults to 'default'."},
                "involved_object": {"type": "string", "description": "Filter events by this object name (e.g. pod name or deployment name)."},
            },
        },
    },
    {
        "name": "get_deployments",
        "description": "List all deployments in a namespace with replica counts and rollout conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace. Defaults to 'default'."},
            },
        },
    },
    {
        "name": "get_deployment",
        "description": "Get detailed information about a specific deployment including container images, resource requests/limits, and rollout conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name."},
                "namespace": {"type": "string", "description": "Namespace. Defaults to 'default'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_nodes",
        "description": "List all cluster nodes with their readiness status, capacity, and conditions. Use this when pods are stuck in Pending or to diagnose node pressure.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_namespaces",
        "description": "List all namespaces in the cluster with their status. Use this to discover available namespaces before querying pods, deployments, or events.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_cronjobs",
        "description": "List all CronJobs in a namespace with their schedule, suspended status, active job count, and last run times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace. Defaults to 'default'.",
                }
            },
        },
    },
    {
        "name": "search_github",
        "description": (
            "Search GitHub issues for a specific error message or exception. "
            "Use this after retrieving pod logs to find known bugs, open issues, or fixes "
            "related to the error. Extract just the key error line before searching — "
            "do not pass the entire log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "The specific error or exception text to search for.",
                },
                "repo": {
                    "type": "string",
                    "description": "Optional GitHub repo in 'owner/repo' format to scope the search.",
                },
            },
            "required": ["error_message"],
        },
    },
    {
        "name": "get_image_git_info",
        "description": (
            "Fetch git metadata (commit SHA, branch, source repo) from a private ECR Docker image "
            "by reading its OCI labels. Use this when you have an image digest from a pod and want "
            "to know which git branch or commit it was built from. "
            "Requires valid AWS credentials (same ones used for EKS access)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_ref": {
                    "type": "string",
                    "description": (
                        "Full ECR image reference, e.g. "
                        "'123456789.dkr.ecr.us-east-1.amazonaws.com/myrepo@sha256:abc...'"
                    ),
                },
            },
            "required": ["image_ref"],
        },
    },
    {
        "name": "find_repo_by_workflow",
        "description": (
            "Find the GitHub repository that builds a given Docker image by searching "
            "GitHub Actions workflow files for the image name. "
            "Use this when get_image_git_info returns a commit SHA but no source repo — "
            "it searches .github/workflows files across GitHub to identify which repo "
            "pushes that image to ECR. Returns the repo name to pass to get_commit_info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_name": {
                    "type": "string",
                    "description": "The Docker image name to search for, e.g. 'carrara-tiledb-server'.",
                },
                "ecr_registry": {
                    "type": "string",
                    "description": (
                        "Optional ECR registry hostname to narrow the search, "
                        "e.g. '980565411111.dkr.ecr.us-east-1.amazonaws.com'."
                    ),
                },
            },
            "required": ["image_name"],
        },
    },
    {
        "name": "get_commit_info",
        "description": (
            "Look up a specific git commit and find which branch and repo it belongs to. "
            "Use this after get_image_git_info returns a commit SHA. "
            "If repo is omitted, searches GitHub globally by commit hash to discover the repo automatically. "
            "Returns commit message, author, date, source branch, and associated pull requests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "commit_sha": {
                    "type": "string",
                    "description": "The git commit SHA to look up (full or short, e.g. 'a020c2d5').",
                },
                "repo": {
                    "type": "string",
                    "description": (
                        "Optional GitHub repository in 'owner/repo' format. "
                        "If omitted, a global search is performed to find the repo automatically."
                    ),
                },
            },
            "required": ["commit_sha"],
        },
    },
    {
        "name": "get_github_file_content",
        "description": (
            "Fetch lines from a file in a GitHub repository. "
            "Use start_line/end_line to jump directly to a line number from a stack trace. "
            "Use search_term to find all occurrences of a string with surrounding context. "
            "Optionally scope to a specific branch or commit SHA."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "GitHub repository in 'owner/repo' format.",
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file within the repository, e.g. 'src/server/main.py'.",
                },
                "search_term": {
                    "type": "string",
                    "description": "String to search for. Returns all matching lines with 5 lines of context.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-based). Use with end_line to fetch a specific range.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (1-based, inclusive).",
                },
                "ref": {
                    "type": "string",
                    "description": "Branch, tag, or commit SHA to fetch from. Defaults to the repo's default branch.",
                },
            },
            "required": ["repo", "path"],
        },
    },
    {
        "name": "search_github_code",
        "description": (
            "Search source code in a specific GitHub repository for an error string. "
            "Use this to find if an error message exists in your own repo's source code. "
            "Requires a specific repo in 'owner/repo' format."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "The error text to search for in source code.",
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub repository in 'owner/repo' format (required).",
                },
            },
            "required": ["error_message", "repo"],
        },
    },
    {
        "name": "search_github_commits",
        "description": (
            "Search commit messages in a specific GitHub repository for an error string. "
            "Use this to find which commit introduced a bug or error. "
            "Requires a specific repo in 'owner/repo' format."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "The error text to search for in commit messages.",
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub repository in 'owner/repo' format (required).",
                },
            },
            "required": ["error_message", "repo"],
        },
    },
]


def dispatch(
    tool_name: str,
    tool_input: dict,
    core_api: k8s_client.CoreV1Api,
    apps_api: k8s_client.AppsV1Api,
    batch_api: k8s_client.BatchV1Api,
) -> dict:
    """Route a tool call to its implementation."""
    ns = tool_input.get("namespace", "default")

    match tool_name:
        case "get_pods":
            return get_pods(core_api, namespace=ns)
        case "describe_pod":
            return describe_pod(core_api, name=tool_input["name"], namespace=ns)
        case "get_pod_logs":
            return get_pod_logs(
                core_api,
                name=tool_input["name"],
                namespace=ns,
                container=tool_input.get("container"),
                tail_lines=tool_input.get("tail_lines", 100),
                previous=tool_input.get("previous", False),
            )
        case "get_events":
            return get_events(core_api, namespace=ns, involved_object=tool_input.get("involved_object"))
        case "get_deployments":
            return get_deployments(apps_api, namespace=ns)
        case "get_deployment":
            return get_deployment(apps_api, name=tool_input["name"], namespace=ns)
        case "get_nodes":
            return get_nodes(core_api)
        case "list_namespaces":
            return list_namespaces(core_api)
        case "get_cronjobs":
            return get_cronjobs(batch_api, namespace=ns)
        case "search_github":
            return search_github(
                error_message=tool_input["error_message"],
                repo=tool_input.get("repo"),
            )
        case "get_image_git_info":
            return get_image_git_info(image_ref=tool_input["image_ref"])
        case "find_repo_by_workflow":
            return find_repo_by_workflow(
                image_name=tool_input["image_name"],
                ecr_registry=tool_input.get("ecr_registry"),
            )
        case "get_commit_info":
            return get_commit_info(
                commit_sha=tool_input["commit_sha"],
                repo=tool_input.get("repo"),
            )
        case "get_github_file_content":
            return get_github_file_content(
                repo=tool_input["repo"],
                path=tool_input["path"],
                search_term=tool_input.get("search_term"),
                ref=tool_input.get("ref"),
                start_line=tool_input.get("start_line"),
                end_line=tool_input.get("end_line"),
            )
        case "search_github_code":
            return search_github_code(
                error_message=tool_input["error_message"],
                repo=tool_input["repo"],
            )
        case "search_github_commits":
            return search_github_commits(
                error_message=tool_input["error_message"],
                repo=tool_input["repo"],
            )
        case _:
            return {"error": f"Unknown tool: {tool_name}"}
