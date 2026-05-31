"""Safe local filesystem helpers for explicit CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "localmind.egg-info",
    "references",
}
PROTECTED_ROOTS = (Path("/proc"), Path("/sys"), Path("/dev"))
PROTECTED_FILES = {Path("/etc/shadow")}
_BINARY_SAMPLE_BYTES = 4096


class FilesystemSafetyError(RuntimeError):
    """Base error for explicit filesystem safety failures."""


class UnsafePathError(FilesystemSafetyError):
    """Raised when a path resolves to a blocked location."""


class HiddenFileError(FilesystemSafetyError):
    """Raised when hidden files are blocked by default."""


class BinaryFileError(FilesystemSafetyError):
    """Raised when a file appears to be binary."""


class FileTooLargeError(FilesystemSafetyError):
    """Raised when a file exceeds the configured size limit."""


@dataclass(slots=True)
class TextFileReadResult:
    path: Path
    text: str
    size_bytes: int
    truncated: bool
    language_hint: str


@dataclass(slots=True)
class SearchMatch:
    path: Path
    line_number: int
    line_text: str


@dataclass(slots=True)
class ProjectContextFile:
    path: Path
    size_bytes: int
    text: str
    truncated: bool


@dataclass(slots=True)
class ProjectContext:
    root: Path
    files: list[ProjectContextFile]


def resolve_safe_path(path: str | Path, *, must_exist: bool = True) -> Path:
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise FilesystemSafetyError(f"Failed to resolve path {candidate}: {exc}") from exc
    if is_protected_path(resolved):
        raise UnsafePathError(f"Refusing to access protected path: {resolved}")
    return resolved


def is_protected_path(path: Path) -> bool:
    if path in PROTECTED_FILES:
        return True
    return any(_is_relative_to(path, root) for root in PROTECTED_ROOTS)


def is_ignored_directory(path: Path) -> bool:
    return path.name in IGNORED_DIRECTORY_NAMES


def is_hidden_directory(path: Path) -> bool:
    return path.name.startswith(".")


def is_hidden_file(path: Path) -> bool:
    return path.name.startswith(".")


def detect_language_hint(path: Path) -> str:
    if path.name == "README.md":
        return "markdown"
    if path.name == "pyproject.toml":
        return "toml"
    if path.suffix:
        return path.suffix.lstrip(".").lower()
    return "text"


def file_size_bytes(path: Path) -> int:
    return path.stat().st_size


def is_binary_file(path: Path) -> bool:
    with path.open("rb") as handle:
        sample = handle.read(_BINARY_SAMPLE_BYTES)
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def read_safe_text_file(
    path: str | Path,
    *,
    max_file_bytes: int,
    max_chars: int | None = None,
    allow_hidden: bool = False,
) -> TextFileReadResult:
    resolved = resolve_safe_path(path)
    if resolved.is_dir():
        raise FilesystemSafetyError(f"Expected a file, not a directory: {resolved}")
    if not allow_hidden and is_hidden_file(resolved):
        raise HiddenFileError(f"Refusing to read hidden file by default: {resolved.name}")

    size_bytes = file_size_bytes(resolved)
    if size_bytes > max_file_bytes:
        raise FileTooLargeError(
            f"Refusing to read {resolved}: {size_bytes} bytes exceeds limit {max_file_bytes}"
        )
    if is_binary_file(resolved):
        raise BinaryFileError(f"Refusing to read binary file: {resolved}")

    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BinaryFileError(f"Refusing to read non-UTF-8 text file: {resolved}") from exc
    truncated = False
    if max_chars is not None:
        text, truncated = truncate_text(text, max_chars)

    return TextFileReadResult(
        path=resolved,
        text=text,
        size_bytes=size_bytes,
        truncated=truncated,
        language_hint=detect_language_hint(resolved),
    )


def walk_project_files(path: str | Path, *, max_depth: int, max_files: int) -> list[Path]:
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_files < 1:
        raise ValueError("max_files must be at least 1")

    root = resolve_safe_path(path)
    if root.is_file():
        return [root]

    files: list[Path] = []
    for current in _iter_project_paths(root, max_depth=max_depth):
        if current.is_file():
            files.append(current)
            if len(files) >= max_files:
                break
    return files


def search_text_files(
    path: str | Path,
    query: str,
    *,
    max_depth: int,
    max_files: int,
    max_results: int,
    max_file_bytes: int,
) -> list[SearchMatch]:
    matches: list[SearchMatch] = []
    for file_path in walk_project_files(path, max_depth=max_depth, max_files=max_files):
        try:
            result = read_safe_text_file(file_path, max_file_bytes=max_file_bytes, allow_hidden=False)
        except FilesystemSafetyError:
            continue

        for line_number, line in enumerate(result.text.splitlines(), start=1):
            if query in line:
                matches.append(
                    SearchMatch(path=file_path, line_number=line_number, line_text=line.strip())
                )
                if len(matches) >= max_results:
                    return matches
    return matches


def collect_project_context(
    path: str | Path,
    *,
    max_depth: int,
    max_files: int,
    max_chars_per_file: int,
    max_file_bytes: int,
    max_total_chars: int = 5_000,
) -> ProjectContext:
    root = resolve_safe_path(path)
    all_files = walk_project_files(root, max_depth=max_depth, max_files=max(max_files * 4, max_files))
    prioritized = sorted(all_files, key=lambda item: (_project_priority(root, item), str(item.relative_to(root))))

    context_files: list[ProjectContextFile] = []
    total_chars = 0
    for file_path in prioritized:
        remaining_chars = max_total_chars - total_chars
        if remaining_chars <= 0:
            break
        try:
            result = read_safe_text_file(
                file_path,
                max_file_bytes=max_file_bytes,
                max_chars=min(max_chars_per_file, remaining_chars),
                allow_hidden=False,
            )
        except FilesystemSafetyError:
            continue

        context_files.append(
            ProjectContextFile(
                path=file_path,
                size_bytes=result.size_bytes,
                text=result.text,
                truncated=result.truncated,
            )
        )
        total_chars += len(result.text)
        if len(context_files) >= max_files:
            break

    return ProjectContext(root=root, files=context_files)


def build_file_summary_prompt(file_result: TextFileReadResult) -> str:
    truncation_note = "yes" if file_result.truncated else "no"
    return (
        "You are LocalMind, a local-first AI assistant. Summarize the following file for a developer. "
        "Be concise but useful. Mention purpose, important functions/classes/configuration, and any "
        "obvious concerns. Do not invent details that are not present.\n\n"
        f"File path: {file_result.path}\n"
        f"Language/type: {file_result.language_hint}\n"
        f"Truncated: {truncation_note}\n\n"
        "File content:\n"
        f"{file_result.text}"
    )


def build_project_summary_prompt(context: ProjectContext) -> str:
    lines = [
        "You are LocalMind, a local-first AI assistant. Analyze this compact project context. Explain "
        "what the project does, its main technologies, important files, and practical next steps. Be "
        "clear and concise. Do not claim you read files that were not included.",
        "",
        f"Project path: {context.root}",
        "Included files:",
    ]

    for item in context.files:
        relative_path = item.path.relative_to(context.root)
        lines.append(f"- {relative_path} ({item.size_bytes} bytes, truncated={'yes' if item.truncated else 'no'})")

    lines.append("")
    lines.append("Project context:")
    for item in context.files:
        relative_path = item.path.relative_to(context.root)
        lines.append("")
        lines.append(f"## {relative_path}")
        lines.append(item.text)

    return "\n".join(lines)


def _iter_project_paths(root: Path, *, max_depth: int) -> list[Path]:
    stack = [root]
    collected: list[Path] = []
    while stack:
        current = stack.pop()
        if current != root and _relative_depth(root, current) > max_depth:
            continue
        collected.append(current)
        if current.is_dir():
            try:
                children = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
            except OSError:
                continue
            for child in reversed(children):
                if _should_skip_walk_child(child):
                    continue
                stack.append(child)
    return collected


def _should_skip_walk_child(path: Path) -> bool:
    if _resolves_to_protected_path(path):
        return True
    if path.is_dir() and (is_ignored_directory(path) or is_hidden_directory(path)):
        return True
    if path.is_file() and is_hidden_file(path):
        return True
    return False


def _resolves_to_protected_path(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return False
    return is_protected_path(resolved)


def _project_priority(root: Path, path: Path) -> tuple[int, int, str]:
    relative = path.relative_to(root)
    normalized = relative.as_posix()
    priority_names = {
        "README.md": 0,
        "pyproject.toml": 1,
        "package.json": 2,
        "requirements.txt": 3,
        "main.py": 4,
        "app.py": 5,
    }
    if normalized in priority_names:
        return (0, priority_names[normalized], normalized)
    if normalized.startswith("src/"):
        return (1, 0, normalized)
    if normalized.startswith("localmind/"):
        return (1, 1, normalized)
    return (2, _relative_depth(root, path), normalized)


def _relative_depth(root: Path, path: Path) -> int:
    return len(path.relative_to(root).parts)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
