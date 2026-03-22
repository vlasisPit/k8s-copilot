"""
Unit tests for Kubernetes tools.
All Kubernetes API calls are mocked — no real cluster required.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from src.tools.cronjobs import get_cronjobs
from src.tools.deployments import get_deployment, get_deployments
from src.tools.events import get_events
from src.tools.namespaces import list_namespaces
from src.tools.nodes import get_nodes
from src.tools.pods import describe_pod, get_pod_logs, get_pods
from src.tools.utils import k8s_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_api_exception(status: int, message: str) -> ApiException:
    """Build a Kubernetes ApiException with a JSON body."""
    e = ApiException(status=status, reason="Not Found")
    e.body = json.dumps({"message": message})
    return e


# ---------------------------------------------------------------------------
# k8s_error utility
# ---------------------------------------------------------------------------


def test_k8s_error_parses_api_exception():
    e = make_api_exception(404, 'pods "my-pod" not found')
    assert k8s_error(e) == 'pods "my-pod" not found'


def test_k8s_error_falls_back_on_plain_exception():
    assert k8s_error(ValueError("something went wrong")) == "something went wrong"


def test_k8s_error_falls_back_on_invalid_json():
    e = ApiException(status=500, reason="Internal Server Error")
    e.body = "not valid json"
    assert k8s_error(e) == "HTTP 500: Internal Server Error"


# ---------------------------------------------------------------------------
# get_pods
# ---------------------------------------------------------------------------


def test_get_pods_returns_pod_list():
    mock_api = MagicMock()

    pod = MagicMock()
    pod.metadata.name = "web-abc123"
    pod.metadata.namespace = "default"
    pod.status.phase = "Running"
    pod.spec.node_name = "node-1"

    cs = MagicMock()
    cs.name = "web"
    cs.ready = True
    cs.restart_count = 0
    cs.state.running = True
    cs.state.waiting = None
    cs.state.terminated = None
    pod.status.container_statuses = [cs]

    mock_api.list_namespaced_pod.return_value.items = [pod]

    result = get_pods(mock_api, namespace="default")

    assert result["count"] == 1
    assert result["pods"][0]["name"] == "web-abc123"
    assert result["pods"][0]["containers"][0]["state"] == "running"


def test_get_pods_returns_error_on_api_exception():
    mock_api = MagicMock()
    mock_api.list_namespaced_pod.side_effect = make_api_exception(403, "forbidden")

    result = get_pods(mock_api, namespace="default")

    assert "error" in result
    assert result["error"] == "forbidden"


# ---------------------------------------------------------------------------
# describe_pod
# ---------------------------------------------------------------------------


def test_describe_pod_returns_pod_details():
    mock_api = MagicMock()

    pod = MagicMock()
    pod.metadata.name = "web-abc123"
    pod.metadata.namespace = "default"
    pod.metadata.labels = {"app": "web"}
    pod.status.phase = "Running"
    pod.spec.node_name = "node-1"
    pod.status.start_time = "2026-01-01T00:00:00Z"
    pod.status.conditions = []
    pod.status.container_statuses = []

    mock_api.read_namespaced_pod.return_value = pod

    result = describe_pod(mock_api, name="web-abc123", namespace="default")

    assert result["name"] == "web-abc123"
    assert result["phase"] == "Running"


def test_describe_pod_returns_error_when_not_found():
    mock_api = MagicMock()
    mock_api.read_namespaced_pod.side_effect = make_api_exception(404, 'pods "missing-pod" not found')

    result = describe_pod(mock_api, name="missing-pod")

    assert "error" in result
    assert "missing-pod" in result["error"]


# ---------------------------------------------------------------------------
# get_pod_logs
# ---------------------------------------------------------------------------


def test_get_pod_logs_returns_logs():
    mock_api = MagicMock()
    mock_api.read_namespaced_pod_log.return_value = "line1\nline2\nline3"

    result = get_pod_logs(mock_api, name="web-abc123", namespace="default")

    assert result["logs"] == "line1\nline2\nline3"
    assert result["pod"] == "web-abc123"


def test_get_pod_logs_returns_error_when_pod_not_found():
    mock_api = MagicMock()
    mock_api.read_namespaced_pod_log.side_effect = make_api_exception(404, 'pods "gone-pod" not found')

    result = get_pod_logs(mock_api, name="gone-pod")

    assert "error" in result
    assert result["pod"] == "gone-pod"


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------


def test_get_events_returns_events():
    mock_api = MagicMock()

    event = MagicMock()
    event.type = "Warning"
    event.reason = "BackOff"
    event.message = "Back-off restarting failed container"
    event.involved_object.kind = "Pod"
    event.involved_object.name = "web-abc123"
    event.count = 5
    event.first_timestamp = "2026-01-01T00:00:00Z"
    event.last_timestamp = "2026-01-01T01:00:00Z"

    mock_api.list_namespaced_event.return_value.items = [event]

    result = get_events(mock_api, namespace="default")

    assert result["count"] == 1
    assert result["events"][0]["reason"] == "BackOff"
    assert result["events"][0]["type"] == "Warning"


def test_get_events_filters_by_involved_object():
    mock_api = MagicMock()

    def make_event(name):
        e = MagicMock()
        e.type = "Warning"
        e.reason = "BackOff"
        e.message = "msg"
        e.involved_object.kind = "Pod"
        e.involved_object.name = name
        e.count = 1
        e.first_timestamp = "2026-01-01T00:00:00Z"
        e.last_timestamp = "2026-01-01T00:00:00Z"
        return e

    mock_api.list_namespaced_event.return_value.items = [
        make_event("pod-a"),
        make_event("pod-b"),
    ]

    result = get_events(mock_api, namespace="default", involved_object="pod-a")

    assert result["count"] == 1
    assert result["events"][0]["object"] == "Pod/pod-a"


# ---------------------------------------------------------------------------
# get_nodes
# ---------------------------------------------------------------------------


def test_get_nodes_returns_ready_node():
    mock_api = MagicMock()

    node = MagicMock()
    node.metadata.name = "node-1"
    node.metadata.labels = {}

    condition = MagicMock()
    condition.type = "Ready"
    condition.status = "True"
    condition.reason = "KubeletReady"
    node.status.conditions = [condition]
    node.status.capacity = {"cpu": "4", "memory": "16Gi", "pods": "110"}
    node.status.allocatable = {"cpu": "3.9", "memory": "15Gi", "pods": "110"}

    mock_api.list_node.return_value.items = [node]

    result = get_nodes(mock_api)

    assert result["count"] == 1
    assert result["nodes"][0]["ready"] is True


# ---------------------------------------------------------------------------
# list_namespaces
# ---------------------------------------------------------------------------


def test_list_namespaces_returns_namespaces():
    mock_api = MagicMock()

    ns = MagicMock()
    ns.metadata.name = "tiledb"
    ns.metadata.labels = {}
    ns.status.phase = "Active"

    mock_api.list_namespace.return_value.items = [ns]

    result = list_namespaces(mock_api)

    assert result["count"] == 1
    assert result["namespaces"][0]["name"] == "tiledb"


# ---------------------------------------------------------------------------
# get_deployments
# ---------------------------------------------------------------------------


def test_get_deployments_returns_deployment_list():
    mock_api = MagicMock()

    d = MagicMock()
    d.metadata.name = "web"
    d.metadata.namespace = "default"
    d.spec.replicas = 3
    d.status.ready_replicas = 3
    d.status.available_replicas = 3
    d.status.updated_replicas = 3
    d.status.conditions = []

    mock_api.list_namespaced_deployment.return_value.items = [d]

    result = get_deployments(mock_api, namespace="default")

    assert result["count"] == 1
    assert result["deployments"][0]["name"] == "web"
    assert result["deployments"][0]["replicas"]["ready"] == 3


# ---------------------------------------------------------------------------
# get_cronjobs
# ---------------------------------------------------------------------------


def test_get_cronjobs_returns_cronjob_list():
    mock_api = MagicMock()

    cj = MagicMock()
    cj.metadata.name = "daily-backup"
    cj.metadata.namespace = "default"
    cj.spec.schedule = "0 2 * * *"
    cj.spec.suspend = False
    cj.status.active = []
    cj.status.last_schedule_time = None
    cj.status.last_successful_time = None

    mock_api.list_namespaced_cron_job.return_value.items = [cj]

    result = get_cronjobs(mock_api, namespace="default")

    assert result["count"] == 1
    assert result["cronjobs"][0]["name"] == "daily-backup"
    assert result["cronjobs"][0]["schedule"] == "0 2 * * *"
    assert result["cronjobs"][0]["suspended"] is False