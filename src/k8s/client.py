import os
from kubernetes import client, config


def load_kube_client() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    """Load Kubernetes client from kubeconfig or in-cluster config.

    Env vars:
      KUBECONFIG         — path to a kubeconfig file (defaults to ~/.kube/config)
      KUBECONFIG_CONTEXT — context name to use (defaults to the active context)
    """
    kubeconfig = os.getenv("KUBECONFIG")
    context = os.getenv("KUBECONFIG_CONTEXT")

    try:
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig, context=context)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config(context=context)
    except Exception as e:
        raise RuntimeError(f"Failed to load Kubernetes config: {e}") from e

    return client.CoreV1Api(), client.AppsV1Api()
