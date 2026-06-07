import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from xml.etree import ElementTree

from .models import Finding, LintResult


def render_report(result: LintResult, fmt: str) -> str:
    if fmt == "json":
        return render_json(result)
    if fmt == "junit":
        return render_junit(result)
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
            }
            for finding in result.findings
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
        return "\n".join(lines) + "\n"
    lines.extend(["## Findings", ""])
    for finding in result.findings:
        location = f"{finding.path}:{finding.line}"
        lines.append(f"- **{finding.severity.upper()}** `{finding.rule_id}` at `{location}`")
        lines.append(f"  {finding.message}")
    return "\n".join(lines) + "\n"


def render_junit(result: LintResult) -> str:
    suite = ElementTree.Element(
        "testsuite",
        {
            "name": "agent-runbook-linter",
            "tests": str(max(1, len(result.findings))),
            "failures": str(len(result.findings)),
            "errors": "0",
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
    xml = ElementTree.tostring(suite, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"
