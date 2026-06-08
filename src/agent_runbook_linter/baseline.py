import hashlib
import json
from pathlib import Path
from typing import Iterable, Set

from . import __version__
from .models import Finding, LintResult, SEVERITY_ORDER


def fingerprint_finding(finding: Finding) -> str:
    payload = {
        "rule_id": finding.rule_id,
        "path": _normalize_path(finding.path),
        "line": int(finding.line or 1),
        "message": " ".join(finding.message.split()),
        "details": finding.details,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def attach_fingerprints(result: LintResult) -> LintResult:
    for finding in result.findings:
        if not finding.fingerprint:
            object.__setattr__(finding, "fingerprint", fingerprint_finding(finding))
    for finding in result.suppressed_findings:
        if not finding.fingerprint:
            object.__setattr__(finding, "fingerprint", fingerprint_finding(finding))
    return result


def load_baseline(path: Path) -> Set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("findings", [])
    else:
        raise ValueError("baseline must be a JSON object or list")

    fingerprints = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fingerprint = entry.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            fingerprints.add(fingerprint)
    return fingerprints


def apply_baseline(result: LintResult, fingerprints: Iterable[str]) -> LintResult:
    known = set(fingerprints)
    attach_fingerprints(result)
    kept = []
    suppressed = []
    for finding in result.findings:
        if finding.fingerprint in known:
            suppressed.append(finding)
        else:
            kept.append(finding)
    result.findings = kept
    result.suppressed_findings = suppressed
    return result


def render_baseline(result: LintResult) -> str:
    attach_fingerprints(result)
    data = {
        "schema_version": 1,
        "generated_by": "agent-runbook-linter",
        "tool_version": __version__,
        "description": "Known agent runbook findings. Review before committing; CI can use this file to fail only on new findings.",
        "finding_count": len(result.findings),
        "blocking_finding_count": sum(1 for finding in result.findings if finding.level() >= SEVERITY_ORDER["warning"]),
        "findings": [
            {
                "fingerprint": finding.fingerprint,
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "message": finding.message,
                "path": _normalize_path(finding.path),
                "line": int(finding.line or 1),
                "details": finding.details,
            }
            for finding in sorted(result.findings, key=lambda item: (item.rule_id, item.path, item.line, item.fingerprint))
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    return normalized
