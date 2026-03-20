from kubernetes import client


def list_namespaces(core_api: client.CoreV1Api) -> dict:
    """List all namespaces in the cluster with their status."""
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