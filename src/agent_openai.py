"""Agent loop backed by OpenAI (gpt-4o by default)."""

import json
import os

from kubernetes import client as k8s_client
from openai import OpenAI

from .tools import TOOLS, dispatch

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = """You are a Kubernetes expert assistant. You help engineers troubleshoot
cluster issues by querying the Kubernetes API and reasoning about what you find.

When asked about a problem:
1. Gather relevant context using available tools (pods, logs, events, deployments, nodes)
2. Look for patterns: CrashLoopBackOff, OOMKilled, Pending pods, image pull errors, etc.
3. Explain the root cause clearly in plain English
4. Suggest concrete remediation steps

Always check events alongside pod/deployment status — they often contain the most useful signal.
Be concise but thorough. If you need more information, ask the user."""

_OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOLS
]


def run(
    messages: list[dict],
    core_api: k8s_client.CoreV1Api,
    apps_api: k8s_client.AppsV1Api,
) -> str:
    client = OpenAI()
    current_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages.copy()

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            tools=_OPENAI_TOOLS,
            messages=current_messages,
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            return message.content or ""

        current_messages.append(message)

        for tool_call in tool_calls:
            tool_input = json.loads(tool_call.function.arguments)
            result = dispatch(tool_call.function.name, tool_input, core_api, apps_api)
            current_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })