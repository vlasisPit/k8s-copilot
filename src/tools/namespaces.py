from kubernetes import client

from .utils import k8s_error


def list_namespaces(core_api: client.CoreV1Api) -> dict:
    """List all namespaces in the cluster with their status."""
    try:
        namespaces = core_api.list_namespace()
        result = [
            {
                "name": ns.metadata.name,
                "status": ns.status.phase,
                "labels": ns.metadata.labels,
            }
            for ns in namespaces.items
        ]
        return {"namespaces": result, "count": len(result)}
    except Exception as e:
        return {"error": k8s_error(e)}
