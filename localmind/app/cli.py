"""Typer CLI for LocalMind."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from localmind.app.bootstrap import build_runtime, write_default_config
from localmind.config.loader import dump_config, load_config
from localmind.core.session import SessionNotFoundError
from localmind.llm.base import ProviderConnectionError

app = typer.Typer(help="LocalMind CLI")
config_app = typer.Typer(help="Inspect configuration")
models_app = typer.Typer(help="Model connectivity commands")
sessions_app = typer.Typer(help="Manage persistent chat sessions")
console = Console()
error_console = Console(stderr=True)

app.add_typer(config_app, name="config")
app.add_typer(models_app, name="models")
app.add_typer(sessions_app, name="sessions")

_CHAT_EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}
_CHAT_STARTUP_TEXT = "Type 'exit', 'quit', '/exit', '/quit', or ':q' to leave."


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
def ask(message: str, session: str | None = typer.Option(None, "--session", help="Append to an existing session.")) -> None:
    """Send one message and print the assistant reply."""
    try:
        reply = asyncio.run(_ask_once(message, session_id=session))
    except (ProviderConnectionError, SessionNotFoundError) as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(reply, markup=False)


@app.command()
def chat(
    session: str | None = typer.Option(None, "--session", help="Resume an existing session."),
    new: bool = typer.Option(False, "--new", help="Start a fresh session."),
) -> None:
    """Start a minimal interactive chat loop."""
    if session is not None and new:
        raise typer.BadParameter("Use either --session or --new, not both.")

    try:
        asyncio.run(_chat_loop(session_id=session, create_session=new or session is None))
    except (ProviderConnectionError, SessionNotFoundError) as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc


@sessions_app.command("list")
def sessions_list() -> None:
    """List saved sessions."""
    try:
        lines = asyncio.run(_sessions_list())
    except SessionNotFoundError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(lines, markup=False)


@sessions_app.command("show")
def sessions_show(session_id: str) -> None:
    """Show one saved session and its messages."""
    try:
        output = asyncio.run(_sessions_show(session_id))
    except SessionNotFoundError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(output, markup=False)


@sessions_app.command("delete")
def sessions_delete(session_id: str) -> None:
    """Delete a saved session."""
    try:
        message = asyncio.run(_sessions_delete(session_id))
    except SessionNotFoundError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(message, markup=False)


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


async def _ask_once(message: str, session_id: str | None = None) -> str:
    async with build_runtime(session_id=session_id) as runtime:
        return await runtime.agent.ask(message, session=runtime.session)


async def _chat_loop(session_id: str | None = None, create_session: bool = True) -> None:
    console.print(f"LocalMind chat started. {_CHAT_STARTUP_TEXT}", markup=False)
    async with build_runtime(session_id=session_id, create_session=create_session) as runtime:
        if runtime.session is None:
            raise RuntimeError("Chat runtime requires a session.")
        console.print(f"Session: {runtime.session.session_id}", markup=False)
        while True:
            try:
                message = typer.prompt("You")
            except EOFError:
                console.print("")
                break

            if _is_internal_exit_command(message):
                break
            if not message.strip():
                continue

            reply = await runtime.agent.ask(message, session=runtime.session)
            console.print(f"Assistant: {reply}", markup=False)


def _is_internal_exit_command(message: str) -> bool:
    return message.strip().lower() in _CHAT_EXIT_COMMANDS


async def _sessions_list() -> str:
    async with build_runtime() as runtime:
        sessions = runtime.sessions.list()
        if not sessions:
            return "No sessions found."
        return "\n".join(
            f"{session.id}\t{session.title}\t{session.updated_at}" for session in sessions
        )


async def _sessions_show(session_id: str) -> str:
    async with build_runtime(session_id=session_id) as runtime:
        if runtime.session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        lines = [
            f"Session: {runtime.session.record.id}",
            f"Title: {runtime.session.record.title}",
            f"Created: {runtime.session.record.created_at}",
            f"Updated: {runtime.session.record.updated_at}",
            "",
        ]
        for message in runtime.session.memory.load_messages(runtime.session.session_id):
            lines.append(f"[{message.created_at}] {message.role}: {message.content}")
        if len(lines) == 5:
            lines.append("No messages.")
        return "\n".join(lines)


async def _sessions_delete(session_id: str) -> str:
    async with build_runtime() as runtime:
        runtime.sessions.delete(session_id)
        return f"Deleted session {session_id}"


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
