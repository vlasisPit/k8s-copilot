import os
import urllib3
from kubernetes import client, config


def load_kube_client() -> tuple[client.CoreV1Api, client.AppsV1Api, client.BatchV1Api]:
    """Load Kubernetes client from kubeconfig or in-cluster config.

    Env vars:
      KUBECONFIG                        — path to a kubeconfig file (defaults to ~/.kube/config)
      KUBECONFIG_CONTEXT                — context name to use (defaults to the active context)
      KUBECONFIG_INSECURE_SKIP_TLS_VERIFY — set to 'true' to disable SSL verification
    """
    kubeconfig = os.getenv("KUBECONFIG")
    context = os.getenv("KUBECONFIG_CONTEXT")
    skip_tls = os.getenv("KUBECONFIG_INSECURE_SKIP_TLS_VERIFY", "false").lower() == "true"

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

    if skip_tls:
        configuration = client.Configuration.get_default_copy()
        configuration.verify_ssl = False
        client.Configuration.set_default(configuration)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return client.CoreV1Api(), client.AppsV1Api(), client.BatchV1Api()
