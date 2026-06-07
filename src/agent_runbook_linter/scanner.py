import fnmatch
from pathlib import Path
from typing import Iterable, List

from .models import Document, LinterConfig


def discover_documents(config: LinterConfig) -> List[Document]:
    root = config.root
    documents: List[Document] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relpath = _relpath(path, root)
        if _matches_any(relpath, config.exclude):
            continue
        if not _matches_any(relpath, config.include):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        if _looks_like_agent_doc(relpath, text):
            documents.append(Document(path=path, relpath=relpath, text=text, lines=text.splitlines()))
    return documents


def _relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _matches_any(relpath: str, patterns: Iterable[str]) -> bool:
    normalized = relpath.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(normalized, normalized_pattern):
            return True
    return False


def _looks_like_agent_doc(relpath: str, text: str) -> bool:
    lower_path = relpath.lower()
    if lower_path.endswith(("agents.md", "claude.md", "codex.md")):
        return True
    if lower_path.startswith(".cursor/rules"):
        return True
    if lower_path.startswith("readme."):
        markers = [
            "agent",
            "codex",
            "claude code",
            "cursor",
            "aider",
            "runbook",
            "ai coding",
        ]
        lower_text = text.lower()
        return any(marker in lower_text for marker in markers)
    return True
