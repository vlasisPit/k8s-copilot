from kubernetes import client


def get_events(
    core_api: client.CoreV1Api,
    namespace: str = "default",
    involved_object: str | None = None,
) -> dict:
    """Get Kubernetes events, optionally filtered by involved object name."""
    events = core_api.list_namespaced_event(namespace=namespace)
    result = []
    for event in events.items:
        if involved_object and event.involved_object.name != involved_object:
            continue
        result.append({
            "type": event.type,
            "reason": event.reason,
            "message": event.message,
            "object": f"{event.involved_object.kind}/{event.involved_object.name}",
            "count": event.count,
            "first_time": str(event.first_timestamp),
            "last_time": str(event.last_timestamp),
        })

    # Sort by last_time descending, warnings first
    result.sort(key=lambda e: (e["type"] != "Warning", e["last_time"]), reverse=False)
    return {"events": result, "count": len(result)}
