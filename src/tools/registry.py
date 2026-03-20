"""
Tool definitions (JSON schema) for Claude's tool use API,
and the dispatcher that routes tool calls to their implementations.
"""

from kubernetes import client as k8s_client

from .deployments import get_deployment, get_deployments
from .events import get_events
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
]


def dispatch(
    tool_name: str,
    tool_input: dict,
    core_api: k8s_client.CoreV1Api,
    apps_api: k8s_client.AppsV1Api,
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
        case _:
            return {"error": f"Unknown tool: {tool_name}"}
