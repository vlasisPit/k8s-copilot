"""Agent loop backed by Anthropic Claude (claude-opus-4-6 by default)."""

import json
import os

import anthropic
from kubernetes import client as k8s_client

from .tools import TOOLS, dispatch

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6")

SYSTEM_PROMPT = """You are a Kubernetes expert assistant. You help engineers troubleshoot
cluster issues by querying the Kubernetes API and reasoning about what you find.

When asked about a problem:
1. Gather relevant context using available tools (pods, logs, events, deployments, nodes)
2. Look for patterns: CrashLoopBackOff, OOMKilled, Pending pods, image pull errors, etc.
3. Explain the root cause clearly in plain English
4. Suggest concrete remediation steps

Always check events alongside pod/deployment status — they often contain the most useful signal.
Be concise but thorough. If you need more information, ask the user."""


def run(
    messages: list[dict],
    core_api: k8s_client.CoreV1Api,
    apps_api: k8s_client.AppsV1Api,
) -> str:
    client = anthropic.Anthropic()
    current_messages = messages.copy()

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=current_messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_uses:
            return text_blocks[0].text if text_blocks else ""

        current_messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            result = dispatch(tool_use.name, tool_use.input, core_api, apps_api)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(result),
            })

        current_messages.append({"role": "user", "content": tool_results})