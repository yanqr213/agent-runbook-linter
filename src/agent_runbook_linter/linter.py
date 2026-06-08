from pathlib import Path
from typing import Optional

from .baseline import attach_fingerprints
from .config import load_config
from .models import LintResult
from .rules import lint_documents
from .scanner import discover_documents


def run_lint(root: Path, config_path: Optional[Path] = None) -> LintResult:
    resolved_root = root.resolve()
    config = load_config(resolved_root, config_path)
    documents = discover_documents(config)
    findings = lint_documents(documents, config)
    return attach_fingerprints(LintResult(root=resolved_root, documents=documents, findings=findings))
