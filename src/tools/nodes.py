from kubernetes import client


def get_nodes(core_api: client.CoreV1Api) -> dict:
    """List all nodes with their status and resource capacity."""
    try:
        nodes = core_api.list_node()
        result = []
        for node in nodes.items:
            conditions = []
            if node.status.conditions:
                for c in node.status.conditions:
                    conditions.append({"type": c.type, "status": c.status, "reason": c.reason})

            ready = any(c["type"] == "Ready" and c["status"] == "True" for c in conditions)
            result.append({
                "name": node.metadata.name,
                "ready": ready,
                "capacity": {
                    "cpu": node.status.capacity.get("cpu"),
                    "memory": node.status.capacity.get("memory"),
                    "pods": node.status.capacity.get("pods"),
                },
                "allocatable": {
                    "cpu": node.status.allocatable.get("cpu"),
                    "memory": node.status.allocatable.get("memory"),
                    "pods": node.status.allocatable.get("pods"),
                },
                "conditions": conditions,
                "labels": node.metadata.labels,
            })
        return {"nodes": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e)}
