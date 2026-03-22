"""CLI entry point — interactive chat loop with conversation history."""

import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.rule import Rule

from .agent import run
from .k8s import load_kube_client

load_dotenv()

console = Console()


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]Error:[/] OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    console.print(Rule("[bold cyan]k8s-copilot[/]"))
    console.print("Connecting to Kubernetes cluster...", style="dim")

    try:
        core_api, apps_api, batch_api = load_kube_client()
        console.print("Connected. [dim]Type your question or 'exit' to quit.[/]\n")
    except RuntimeError as e:
        console.print(f"[bold red]Failed to connect to cluster:[/] {e}")
        sys.exit(1)

    messages: list[dict] = []

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            console.print("Bye.")
            break

        if user_input.lower() == "diagnose":
            user_input = (
                "Perform a complete cluster health check. Follow these steps:\n"
                "1. List all namespaces\n"
                "2. For each namespace, check pods for any that are not Running or Completed\n"
                "3. Check deployments for any with unavailable replicas\n"
                "4. Check recent warning events across namespaces\n"
                "5. Check node health\n"
                "Summarize all issues found, their likely cause, and suggested fixes. "
                "If everything looks healthy, say so clearly."
            )
            console.print("[dim]Running full cluster health check...[/]\n")

        messages.append({"role": "user", "content": user_input})

        def on_tool_call(tool_name: str, tool_input: dict) -> None:
            ns = tool_input.get("namespace", "")
            suffix = f" [dim](namespace: {ns})[/]" if ns else ""
            console.print(f"  [dim cyan]→ {tool_name}[/]{suffix}")

        with console.status("[dim]Thinking...[/]", spinner="dots"):
            try:
                response = run(messages, core_api, apps_api, batch_api, on_tool_call)
            except Exception as e:
                console.print(f"[bold red]Error:[/] {e}")
                messages.pop()  # Remove the failed user message
                continue

        messages.append({"role": "assistant", "content": response})

        console.print()
        console.print(Rule("[bold blue]k8s-copilot[/]", style="blue"))
        console.print(Markdown(response))
        console.print()


if __name__ == "__main__":
    main()
