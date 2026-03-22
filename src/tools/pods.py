from kubernetes import client

from .utils import k8s_error


def get_pods(core_api: client.CoreV1Api, namespace: str = "default") -> dict:
    """List all pods in a namespace with their status."""
    try:
        pods = core_api.list_namespaced_pod(namespace=namespace)
        result = []
        for pod in pods.items:
            containers = []
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    state = "unknown"
                    reason = None
                    if cs.state.running:
                        state = "running"
                    elif cs.state.waiting:
                        state = "waiting"
                        reason = cs.state.waiting.reason
                    elif cs.state.terminated:
                        state = "terminated"
                        reason = cs.state.terminated.reason
                    containers.append({
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": state,
                        "reason": reason,
                    })
            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": containers,
            })
        return {"pods": result, "count": len(result)}
    except Exception as e:
        return {"error": k8s_error(e), "namespace": namespace}


def describe_pod(core_api: client.CoreV1Api, name: str, namespace: str = "default") -> dict:
    """Get detailed information about a specific pod."""
    try:
        pod = core_api.read_namespaced_pod(name=name, namespace=namespace)
        conditions = []
        if pod.status.conditions:
            for c in pod.status.conditions:
                conditions.append({
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                })

        container_statuses = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                last_state = None
                if cs.last_state and cs.last_state.terminated:
                    lt = cs.last_state.terminated
                    last_state = {
                        "reason": lt.reason,
                        "exit_code": lt.exit_code,
                        "message": lt.message,
                        "finished_at": str(lt.finished_at),
                    }
                container_statuses.append({
                    "name": cs.name,
                    "image": cs.image,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "last_state": last_state,
                })

        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "start_time": str(pod.status.start_time),
            "conditions": conditions,
            "container_statuses": container_statuses,
            "labels": pod.metadata.labels,
        }
    except Exception as e:
        return {"error": k8s_error(e), "name": name, "namespace": namespace}


def get_pod_logs(
    core_api: client.CoreV1Api,
    name: str,
    namespace: str = "default",
    container: str | None = None,
    tail_lines: int = 100,
    previous: bool = False,
) -> dict:
    """Fetch logs from a pod container."""
    try:
        logs = core_api.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            previous=previous,
        )
        return {"logs": logs, "pod": name, "container": container, "previous": previous}
    except Exception as e:
        return {"error": k8s_error(e), "pod": name}