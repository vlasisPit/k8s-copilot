from kubernetes import client

from .utils import k8s_error


def get_cronjobs(batch_api: client.BatchV1Api, namespace: str = "default") -> dict:
    """List all CronJobs in a namespace with their schedule and last run status."""
    try:
        cronjobs = batch_api.list_namespaced_cron_job(namespace=namespace)
        result = []
        for cj in cronjobs.items:
            result.append({
                "name": cj.metadata.name,
                "namespace": cj.metadata.namespace,
                "schedule": cj.spec.schedule,
                "suspended": cj.spec.suspend or False,
                "active_jobs": len(cj.status.active) if cj.status.active else 0,
                "last_schedule_time": str(cj.status.last_schedule_time) if cj.status.last_schedule_time else None,
                "last_successful_time": str(cj.status.last_successful_time) if cj.status.last_successful_time else None,
            })
        return {"cronjobs": result, "count": len(result)}
    except Exception as e:
        return {"error": k8s_error(e), "namespace": namespace}
