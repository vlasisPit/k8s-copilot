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

        messages.append({"role": "user", "content": user_input})

        with console.status("[dim]Thinking...[/]", spinner="dots"):
            try:
                response = run(messages, core_api, apps_api, batch_api)
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
