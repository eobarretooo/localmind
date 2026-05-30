"""Typer CLI for LocalMind."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from localmind.app.bootstrap import build_runtime, write_default_config
from localmind.config.loader import dump_config, load_config
from localmind.llm.base import ProviderConnectionError

app = typer.Typer(help="LocalMind CLI")
config_app = typer.Typer(help="Inspect configuration")
models_app = typer.Typer(help="Model connectivity commands")
console = Console()
error_console = Console(stderr=True)

app.add_typer(config_app, name="config")
app.add_typer(models_app, name="models")


@app.command()
def init(force: bool = typer.Option(False, "--force", help="Overwrite localmind.yaml if it exists.")) -> None:
    """Write a local config file from effective defaults."""
    target = Path.cwd() / "localmind.yaml"
    if target.exists() and not force:
        raise typer.BadParameter("localmind.yaml already exists. Use --force to overwrite it.")

    config = load_config()
    write_default_config(target=target, config=config)
    console.print(f"Wrote {target}", markup=False)


@app.command()
def ask(message: str) -> None:
    """Send one message and print the assistant reply."""
    try:
        reply = asyncio.run(_ask_once(message))
    except ProviderConnectionError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(reply, markup=False)


@app.command()
def chat() -> None:
    """Start a minimal interactive chat loop."""
    try:
        asyncio.run(_chat_loop())
    except ProviderConnectionError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc


@config_app.command("show")
def config_show() -> None:
    """Print the effective configuration with secrets redacted."""
    console.print(dump_config(load_config(), redact_secrets=True), markup=False)


@models_app.command("test")
def models_test() -> None:
    """Check provider connectivity and model availability."""
    try:
        result = asyncio.run(_models_test())
    except ProviderConnectionError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(result, markup=False)


async def _ask_once(message: str) -> str:
    async with build_runtime() as runtime:
        return await runtime.agent.ask(message, session=runtime.session)


async def _chat_loop() -> None:
    console.print("LocalMind chat started. Type 'exit' or 'quit' to leave.", markup=False)
    async with build_runtime() as runtime:
        while True:
            try:
                message = typer.prompt("You")
            except EOFError:
                console.print("")
                break

            if message.strip().lower() in {"exit", "quit"}:
                break
            if not message.strip():
                continue

            reply = await runtime.agent.ask(message, session=runtime.session)
            console.print(f"Assistant: {reply}", markup=False)


async def _models_test() -> str:
    async with build_runtime() as runtime:
        report = await runtime.provider_manager.test_connection()

        lines = [f"Connected to {report.base_url}"]
        if report.models:
            if report.configured_model_available:
                lines.append(f"Configured model available: {report.configured_model}")
            else:
                lines.append(f"Configured model not reported by server: {report.configured_model}")
                lines.append("Server models: " + ", ".join(report.models))
        else:
            lines.append("Connected, but server did not return a model list.")
        return "\n".join(lines)


def main() -> None:
    """Console script entrypoint."""
    app()
