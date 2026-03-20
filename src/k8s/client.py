import os
from kubernetes import client, config


def load_kube_client() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    """Load Kubernetes client from kubeconfig or in-cluster config."""
    kubeconfig = os.getenv("KUBECONFIG")
    try:
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
    except Exception as e:
        raise RuntimeError(f"Failed to load Kubernetes config: {e}") from e

    return client.CoreV1Api(), client.AppsV1Api()
