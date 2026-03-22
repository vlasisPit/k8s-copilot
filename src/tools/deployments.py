from kubernetes import client

from .utils import k8s_error


def get_deployments(apps_api: client.AppsV1Api, namespace: str = "default") -> dict:
    """List all deployments in a namespace with rollout status."""
    try:
        deployments = apps_api.list_namespaced_deployment(namespace=namespace)
        result = []
        for d in deployments.items:
            conditions = []
            if d.status.conditions:
                for c in d.status.conditions:
                    conditions.append({"type": c.type, "status": c.status, "reason": c.reason, "message": c.message})
            result.append({
                "name": d.metadata.name,
                "namespace": d.metadata.namespace,
                "replicas": {
                    "desired": d.spec.replicas,
                    "ready": d.status.ready_replicas or 0,
                    "available": d.status.available_replicas or 0,
                    "updated": d.status.updated_replicas or 0,
                },
                "conditions": conditions,
            })
        return {"deployments": result, "count": len(result)}
    except Exception as e:
        return {"error": k8s_error(e), "namespace": namespace}


def get_deployment(apps_api: client.AppsV1Api, name: str, namespace: str = "default") -> dict:
    """Get detailed info about a specific deployment."""
    try:
        d = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
        containers = []
        for c in d.spec.template.spec.containers:
            resources = {}
            if c.resources:
                resources = {
                    "requests": c.resources.requests or {},
                    "limits": c.resources.limits or {},
                }
            containers.append({
                "name": c.name,
                "image": c.image,
                "resources": resources,
            })

        conditions = []
        if d.status.conditions:
            for c in d.status.conditions:
                conditions.append({"type": c.type, "status": c.status, "reason": c.reason, "message": c.message})

        return {
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "replicas": {
                "desired": d.spec.replicas,
                "ready": d.status.ready_replicas or 0,
                "available": d.status.available_replicas or 0,
            },
            "containers": containers,
            "conditions": conditions,
            "labels": d.metadata.labels,
        }
    except Exception as e:
        return {"error": k8s_error(e), "name": name, "namespace": namespace}
