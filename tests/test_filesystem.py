import asyncio
from pathlib import Path

import pytest

from localmind.app import cli
from localmind.config.schema import AppConfig
from localmind.tools.filesystem import (
    BinaryFileError,
    FileTooLargeError,
    HiddenFileError,
    _resolves_to_protected_path,
    read_safe_text_file,
    search_text_files,
    walk_project_files,
)


class _RecordingAgent:
    def __init__(self, reply: str = "summary reply") -> None:
        self.reply = reply
        self.calls: list[tuple[str, object | None]] = []

    async def ask(self, user_message: str, session: object | None = None) -> str:
        self.calls.append((user_message, session))
        return self.reply


class _StubRuntime:
    def __init__(self, agent: _RecordingAgent, max_file_bytes: int = 200_000) -> None:
        self.agent = agent
        self.session = None
        self.config = AppConfig.model_validate({"app": {"max_file_bytes": max_file_bytes}})

    async def __aenter__(self) -> "_StubRuntime":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_ignored_directories_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "ignored.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.js").write_text("ignore me", encoding="utf-8")
    (tmp_path / "src").mkdir()
    kept = tmp_path / "src" / "kept.py"
    kept.write_text("print('ok')\n", encoding="utf-8")

    files = walk_project_files(tmp_path, max_depth=4, max_files=20)

    assert files == [kept]


def test_hidden_directories_are_skipped_during_walk(tmp_path: Path) -> None:
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "ignored.py").write_text("print('ignore')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    kept = tmp_path / "src" / "kept.py"
    kept.write_text("print('ok')\n", encoding="utf-8")

    files = walk_project_files(tmp_path, max_depth=4, max_files=20)

    assert files == [kept]


def test_symlink_to_protected_location_is_not_traversed(tmp_path: Path) -> None:
    protected_target = Path("/proc") if Path("/proc").exists() else Path("/etc/shadow")
    link_path = tmp_path / "protected-link"
    try:
        link_path.symlink_to(protected_target)
    except OSError:
        pytest.skip("symlinks are not supported in this environment")

    (tmp_path / "safe.txt").write_text("safe\n", encoding="utf-8")

    files = walk_project_files(tmp_path, max_depth=4, max_files=20)

    assert files == [tmp_path / "safe.txt"]


def test_protected_resolution_helper_flags_shadow_path() -> None:
    assert _resolves_to_protected_path(Path("/etc/shadow")) is True


def test_binary_files_are_rejected(tmp_path: Path) -> None:
    binary_file = tmp_path / "image.bin"
    binary_file.write_bytes(b"\x00\x01\x02")

    with pytest.raises(BinaryFileError):
        read_safe_text_file(binary_file, max_file_bytes=10_000)


def test_large_files_are_rejected(tmp_path: Path) -> None:
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 32, encoding="utf-8")

    with pytest.raises(FileTooLargeError):
        read_safe_text_file(large_file, max_file_bytes=8)


def test_hidden_dotfiles_are_rejected_by_read(tmp_path: Path) -> None:
    hidden_file = tmp_path / ".env"
    hidden_file.write_text("SECRET=1\n", encoding="utf-8")

    with pytest.raises(HiddenFileError):
        read_safe_text_file(hidden_file, max_file_bytes=10_000)


def test_safe_text_files_can_be_read(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello\nworld\n", encoding="utf-8")

    result = read_safe_text_file(text_file, max_file_bytes=10_000, max_chars=100)

    assert result.text == "hello\nworld\n"
    assert result.truncated is False
    assert result.language_hint == "txt"


def test_search_returns_matching_lines_with_line_numbers(tmp_path: Path) -> None:
    file_path = tmp_path / "app.py"
    file_path.write_text("first\nLocalMind match\nthird LocalMind\n", encoding="utf-8")

    matches = search_text_files(
        tmp_path,
        "LocalMind",
        max_depth=3,
        max_files=10,
        max_results=10,
        max_file_bytes=10_000,
    )

    assert [(match.line_number, match.line_text) for match in matches] == [
        (2, "LocalMind match"),
        (3, "third LocalMind"),
    ]


def test_project_walking_respects_max_depth_and_max_files(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "a" / "two.txt").write_text("2", encoding="utf-8")
    (tmp_path / "a" / "nested").mkdir()
    (tmp_path / "a" / "nested" / "three.txt").write_text("3", encoding="utf-8")

    shallow_files = walk_project_files(tmp_path, max_depth=2, max_files=10)
    limited_files = walk_project_files(tmp_path, max_depth=4, max_files=2)

    assert tmp_path / "a" / "nested" / "three.txt" not in shallow_files
    assert len(limited_files) == 2


def test_summarize_prompt_includes_file_content_and_file_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("# Demo\nHelpful details\n", encoding="utf-8")
    agent = _RecordingAgent()

    monkeypatch.setattr(cli, "build_runtime", lambda **_: _StubRuntime(agent))

    result = asyncio.run(cli._summarize_file(str(file_path), max_chars=500))

    assert result == "summary reply"
    prompt, session = agent.calls[0]
    assert session is None
    assert f"File path: {file_path.resolve()}" in prompt
    assert "Language/type: markdown" in prompt
    assert "# Demo\nHelpful details" in prompt


def test_summarize_project_prompt_includes_compact_project_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "localmind").mkdir()
    (tmp_path / "README.md").write_text("# LocalMind\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "localmind" / "app.py").write_text("print('demo')\n", encoding="utf-8")
    agent = _RecordingAgent(reply="project summary")

    monkeypatch.setattr(cli, "build_runtime", lambda **_: _StubRuntime(agent))

    result = asyncio.run(cli._summarize_project(str(tmp_path), max_files=5, max_chars_per_file=500))

    assert result == "project summary"
    prompt, session = agent.calls[0]
    assert session is None
    assert f"Project path: {tmp_path.resolve()}" in prompt
    assert "Included files:" in prompt
    assert "README.md" in prompt
    assert "pyproject.toml" in prompt
    assert "## localmind/app.py" in prompt
    assert "print('demo')" in prompt
