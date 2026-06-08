import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

from . import __version__
from .models import Finding, LintResult


def render_report(result: LintResult, fmt: str) -> str:
    if fmt == "json":
        return render_json(result)
    if fmt == "junit":
        return render_junit(result)
    if fmt == "sarif":
        return render_sarif(result)
    if fmt == "markdown":
        return render_markdown(result)
    raise ValueError(f"Unsupported format: {fmt}")


def write_report(result: LintResult, fmt: str, output: Optional[Path]) -> str:
    rendered = render_report(result, fmt)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    return rendered


def render_json(result: LintResult) -> str:
    payload = {
        "tool": "agent-runbook-linter",
        "root": str(result.root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "documents": len(result.documents),
            "findings": len(result.findings),
            "counts": result.counts(),
            "suppressed_findings": len(result.suppressed_findings),
            "suppressed_counts": result.suppressed_counts(),
        },
        "documents": [doc.relpath for doc in result.documents],
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "message": finding.message,
                "path": finding.path,
                "line": finding.line,
                "details": finding.details,
                "fingerprint": finding.fingerprint,
            }
            for finding in result.findings
        ],
        "suppressed_findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "message": finding.message,
                "path": finding.path,
                "line": finding.line,
                "details": finding.details,
                "fingerprint": finding.fingerprint,
            }
            for finding in result.suppressed_findings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_markdown(result: LintResult) -> str:
    counts = result.counts()
    lines = [
        "# Agent Runbook Linter Report",
        "",
        f"- Root: `{result.root}`",
        f"- Documents scanned: `{len(result.documents)}`",
        f"- Findings: `{len(result.findings)}`",
        f"- Suppressed by baseline: `{len(result.suppressed_findings)}`",
        f"- Severity counts: error `{counts.get('error', 0)}`, warning `{counts.get('warning', 0)}`, info `{counts.get('info', 0)}`",
        "",
    ]
    if result.documents:
        lines.extend(["## Documents", ""])
        for doc in result.documents:
            lines.append(f"- `{doc.relpath}`")
        lines.append("")
    if not result.findings:
        lines.extend(["## Findings", "", "No findings."])
        if result.suppressed_findings:
            lines.extend(_suppressed_markdown(result))
        return "\n".join(lines) + "\n"
    lines.extend(["## Findings", ""])
    for finding in result.findings:
        location = f"{finding.path}:{finding.line}"
        lines.append(f"- **{finding.severity.upper()}** `{finding.rule_id}` at `{location}`")
        lines.append(f"  - Fingerprint: `{finding.fingerprint}`")
        lines.append(f"  {finding.message}")
    if result.suppressed_findings:
        lines.extend(_suppressed_markdown(result))
    return "\n".join(lines) + "\n"


def render_junit(result: LintResult) -> str:
    suite = ElementTree.Element(
        "testsuite",
        {
            "name": "agent-runbook-linter",
            "tests": str(max(1, len(result.findings))),
            "failures": str(len(result.findings)),
            "errors": "0",
            "skipped": str(len(result.suppressed_findings)),
        },
    )
    if not result.findings:
        ElementTree.SubElement(suite, "testcase", {"name": "no-findings", "classname": "agent-runbook-linter"})
    for finding in result.findings:
        testcase = ElementTree.SubElement(
            suite,
            "testcase",
            {
                "name": finding.rule_id,
                "classname": finding.path,
            },
        )
        failure = ElementTree.SubElement(
            testcase,
            "failure",
            {
                "type": finding.severity,
                "message": finding.message,
            },
        )
        failure.text = f"{finding.path}:{finding.line}: {finding.rule_id}: {finding.message}"
    for finding in result.suppressed_findings:
        testcase = ElementTree.SubElement(
            suite,
            "testcase",
            {
                "name": finding.rule_id,
                "classname": finding.path,
            },
        )
        ElementTree.SubElement(
            testcase,
            "skipped",
            {
                "message": f"suppressed by baseline: {finding.fingerprint}",
            },
        )
    xml = ElementTree.tostring(suite, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


def render_sarif(result: LintResult) -> str:
    rules: Dict[str, Dict[str, Any]] = {}
    for finding in result.findings:
        rules.setdefault(
            finding.rule_id,
            {
                "id": finding.rule_id,
                "name": finding.rule_id,
                "shortDescription": {"text": finding.rule_id},
                "fullDescription": {"text": f"Agent runbook lint rule: {finding.rule_id}."},
                "help": {
                    "text": "Review AI coding agent instructions before merging; clarify commands, permissions, paths, acceptance criteria, and safety constraints."
                },
                "defaultConfiguration": {"level": _sarif_level(finding.severity)},
                "properties": {
                    "severity": finding.severity,
                    "tool": "agent-runbook-linter",
                },
            },
        )
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "agent-runbook-linter",
                        "semanticVersion": __version__,
                        "informationUri": "https://github.com/yanqr213/agent-runbook-linter",
                        "rules": list(rules.values()),
                    }
                },
                "automationDetails": {"id": "agent-runbook-linter"},
                "results": [_finding_to_sarif(finding) for finding in result.findings],
                "properties": {
                    "root": str(result.root),
                    "documents": len(result.documents),
                    "findings": len(result.findings),
                    "counts": result.counts(),
                    "suppressed_findings": len(result.suppressed_findings),
                    "suppressed_counts": result.suppressed_counts(),
                },
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _finding_to_sarif(finding: Finding) -> Dict[str, Any]:
    return {
        "ruleId": finding.rule_id,
        "level": _sarif_level(finding.severity),
        "message": {"text": finding.message},
        "partialFingerprints": {"agentRunbookLinter/v1": finding.fingerprint},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.path.replace("\\", "/")},
                    "region": {"startLine": max(int(finding.line or 1), 1)},
                }
            }
        ],
        "properties": {
            "severity": finding.severity,
            "rule_id": finding.rule_id,
            "details": finding.details,
        },
    }


def _suppressed_markdown(result: LintResult) -> List[str]:
    lines = [
        "",
        "## Suppressed By Baseline",
        "",
    ]
    for finding in result.suppressed_findings:
        location = f"{finding.path}:{finding.line}"
        lines.append(f"- **{finding.severity.upper()}** `{finding.rule_id}` at `{location}`")
        lines.append(f"  - Fingerprint: `{finding.fingerprint}`")
    return lines


def _sarif_level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"
