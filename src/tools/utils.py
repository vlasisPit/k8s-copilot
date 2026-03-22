import json

from kubernetes.client.exceptions import ApiException


def k8s_error(e: Exception) -> str:
    """Extract a plain English message from a Kubernetes ApiException."""
    if isinstance(e, ApiException):
        try:
            body = json.loads(e.body)
            return body.get("message", str(e))
        except Exception:
            return f"HTTP {e.status}: {e.reason}"
    return str(e)
