"""
Agent dispatcher — selects the LLM backend based on the LLM_PROVIDER env var.

Supported values:
  LLM_PROVIDER=openai      (default) requires OPENAI_API_KEY
  LLM_PROVIDER=anthropic            requires ANTHROPIC_API_KEY
"""

import os

from kubernetes import client as k8s_client


def run(
    messages: list[dict],
    core_api: k8s_client.CoreV1Api,
    apps_api: k8s_client.AppsV1Api,
    batch_api: k8s_client.BatchV1Api,
) -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "anthropic":
        from .agent_anthropic import run as _run
    elif provider == "openai":
        from .agent_openai import run as _run
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Choose 'openai' or 'anthropic'.")

    return _run(messages, core_api, apps_api, batch_api)