"""Typer CLI for LocalMind."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from localmind.app.bootstrap import build_runtime, write_default_config
from localmind.config.loader import dump_config, load_config
from localmind.core.session import SessionNotFoundError
from localmind.llm.base import ProviderConnectionError
from localmind.tools.filesystem import (
    BinaryFileError,
    FileTooLargeError,
    FilesystemSafetyError,
    HiddenFileError,
    build_file_summary_prompt,
    build_project_summary_prompt,
    collect_project_context,
    read_safe_text_file,
    search_text_files,
    walk_project_files,
)

app = typer.Typer(help="LocalMind CLI")
config_app = typer.Typer(help="Inspect configuration")
models_app = typer.Typer(help="Model connectivity commands")
sessions_app = typer.Typer(help="Manage persistent chat sessions")
files_app = typer.Typer(help="Safe local file commands")
console = Console()
error_console = Console(stderr=True)

app.add_typer(config_app, name="config")
app.add_typer(models_app, name="models")
app.add_typer(sessions_app, name="sessions")
app.add_typer(files_app, name="files")

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


@files_app.command("list")
def files_list(
    path: str,
    max_files: int = typer.Option(200, "--max-files", min=1, help="Maximum files to show."),
    max_depth: int = typer.Option(4, "--max-depth", min=0, help="Maximum recursive depth."),
) -> None:
    """List files under a path, recursively by default."""
    try:
        files = walk_project_files(path, max_depth=max_depth, max_files=max_files)
    except FilesystemSafetyError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc

    root = Path(path).expanduser().resolve()
    table = Table(title=f"Files under {root}")
    table.add_column("Path")
    table.add_column("Size", justify="right")
    for file_path in files:
        display_path = str(file_path.relative_to(root)) if root.is_dir() and file_path != root else file_path.name
        table.add_row(display_path, str(file_path.stat().st_size))
    if not files:
        console.print(f"No files found under {root}", markup=False)
        return
    console.print(table)


@files_app.command("read")
def files_read(
    file: str,
    max_chars: int = typer.Option(12000, "--max-chars", min=1, help="Maximum characters to print."),
) -> None:
    """Read a safe text file."""
    config = load_config()
    try:
        result = read_safe_text_file(file, max_file_bytes=config.app.max_file_bytes, max_chars=max_chars)
    except (BinaryFileError, FileTooLargeError, FilesystemSafetyError, HiddenFileError) as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc

    console.print(result.text, markup=False)
    if result.truncated:
        console.print(f"\n[truncated to {max_chars} characters]", markup=False)


@files_app.command("search")
def files_search(
    path: str,
    query: str,
    max_results: int = typer.Option(50, "--max-results", min=1, help="Maximum matches to show."),
    max_depth: int = typer.Option(4, "--max-depth", min=0, help="Maximum recursive depth."),
) -> None:
    """Search text files under a path for a query."""
    config = load_config()
    try:
        matches = search_text_files(
            path,
            query,
            max_depth=max_depth,
            max_files=max(200, max_results * 4),
            max_results=max_results,
            max_file_bytes=config.app.max_file_bytes,
        )
    except FilesystemSafetyError as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc

    if not matches:
        console.print("No matches found.", markup=False)
        return

    table = Table(title=f"Search results for {query}")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Text")
    for match in matches:
        table.add_row(str(match.path), str(match.line_number), match.line_text)
    console.print(table)


@files_app.command("summarize")
def files_summarize(
    file: str,
    max_chars: int = typer.Option(12000, "--max-chars", min=1, help="Maximum characters to send."),
    session: str | None = typer.Option(None, "--session", help="Append summary to an existing session."),
) -> None:
    """Summarize a safe text file."""
    try:
        summary = asyncio.run(_summarize_file(file=file, max_chars=max_chars, session_id=session))
    except (ProviderConnectionError, SessionNotFoundError, FilesystemSafetyError) as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(summary, markup=False)


@files_app.command("summarize-project")
def files_summarize_project(
    path: str,
    max_files: int = typer.Option(30, "--max-files", min=1, help="Maximum files to include."),
    max_chars_per_file: int = typer.Option(
        4000,
        "--max-chars-per-file",
        min=1,
        help="Maximum characters per file to send.",
    ),
    session: str | None = typer.Option(None, "--session", help="Append summary to an existing session."),
) -> None:
    """Summarize a project from a compact local context."""
    try:
        summary = asyncio.run(
            _summarize_project(
                path=path,
                max_files=max_files,
                max_chars_per_file=max_chars_per_file,
                session_id=session,
            )
        )
    except (ProviderConnectionError, SessionNotFoundError, FilesystemSafetyError) as exc:
        error_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    console.print(summary, markup=False)


async def _ask_once(message: str, session_id: str | None = None) -> str:
    async with build_runtime(session_id=session_id) as runtime:
        return await runtime.agent.ask(message, session=runtime.session)


async def _summarize_file(file: str, max_chars: int, session_id: str | None = None) -> str:
    async with build_runtime(session_id=session_id) as runtime:
        last_error: ProviderConnectionError | None = None
        for char_budget in _summary_char_budgets(max_chars):
            result = read_safe_text_file(
                file,
                max_file_bytes=runtime.config.app.max_file_bytes,
                max_chars=char_budget,
            )
            prompt = build_file_summary_prompt(result)
            try:
                return await runtime.agent.ask(prompt, session=runtime.session)
            except ProviderConnectionError as exc:
                if not _is_context_limit_error(exc):
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable summarize-file state")


async def _summarize_project(
    path: str,
    max_files: int,
    max_chars_per_file: int,
    session_id: str | None = None,
) -> str:
    async with build_runtime(session_id=session_id) as runtime:
        last_error: ProviderConnectionError | None = None
        for total_char_budget in _project_context_budgets(max_chars_per_file=max_chars_per_file, max_files=max_files):
            context = collect_project_context(
                path,
                max_depth=4,
                max_files=max_files,
                max_chars_per_file=max_chars_per_file,
                max_file_bytes=runtime.config.app.max_file_bytes,
                max_total_chars=total_char_budget,
            )
            prompt = build_project_summary_prompt(context)
            try:
                return await runtime.agent.ask(prompt, session=runtime.session)
            except ProviderConnectionError as exc:
                if not _is_context_limit_error(exc):
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable summarize-project state")


def _summary_char_budgets(max_chars: int) -> list[int]:
    budgets: list[int] = []
    for budget in (max_chars, min(max_chars, 4000), min(max_chars, 2000), min(max_chars, 1000)):
        if budget not in budgets:
            budgets.append(budget)
    return budgets


def _project_context_budgets(max_chars_per_file: int, max_files: int) -> list[int]:
    requested_budget = max_chars_per_file * max_files
    budgets: list[int] = []
    for budget in (min(requested_budget, 5000), min(requested_budget, 3000), min(requested_budget, 1500)):
        if budget > 0 and budget not in budgets:
            budgets.append(budget)
    return budgets


def _is_context_limit_error(error: ProviderConnectionError) -> bool:
    message = str(error).lower()
    return "context size" in message or "context" in message and "exceed" in message


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
