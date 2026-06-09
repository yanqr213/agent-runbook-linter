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
    if fmt == "fix-plan":
        return render_fix_plan(result)
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


def render_fix_plan(result: LintResult) -> str:
    counts = result.counts()
    active_findings = _dedupe_fix_findings(result.findings)
    lines = [
        "# Agent Runbook Fix Plan",
        "",
        f"- Root: `{result.root}`",
        f"- Documents scanned: `{len(result.documents)}`",
        f"- Active findings: `{len(result.findings)}`",
        f"- Work items: `{len(active_findings)}`",
        f"- Suppressed by baseline: `{len(result.suppressed_findings)}`",
        f"- Severity counts: error `{counts.get('error', 0)}`, warning `{counts.get('warning', 0)}`, info `{counts.get('info', 0)}`",
        "",
    ]
    if not active_findings:
        lines.extend(
            [
                "## Decision",
                "",
                "No active runbook fixes are required. Keep the current baseline under review if suppressed findings remain.",
                "",
            ]
        )
        if result.suppressed_findings:
            lines.extend(_suppressed_markdown(result))
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "## Recommended Order",
            "",
            "1. Fix `error` findings that can make agents unsafe, unverifiable, or unable to run.",
            "2. Fix `warning` findings that reduce reproducibility or reviewer confidence.",
            "3. Regenerate the baseline only after humans accept any remaining risk.",
            "",
            "## File Work Items",
            "",
        ]
    )
    for path, findings in _findings_by_path(active_findings).items():
        lines.append(f"### `{path}`")
        lines.append("")
        for finding in findings:
            lines.extend(_finding_fix_block(finding))
        lines.append("")
    lines.extend(_agent_prompt(active_findings))
    if result.suppressed_findings:
        lines.extend(_suppressed_markdown(result))
    return "\n".join(lines).rstrip() + "\n"


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


def _findings_by_path(findings: Iterable[Finding]) -> Dict[str, List[Finding]]:
    grouped: Dict[str, List[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.path, []).append(finding)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _dedupe_fix_findings(findings: Iterable[Finding]) -> List[Finding]:
    seen = set()
    result: List[Finding] = []
    for finding in findings:
        key = (finding.path, finding.line, finding.rule_id, finding.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _finding_fix_block(finding: Finding) -> List[str]:
    location = f"{finding.path}:{finding.line}"
    lines = [
        f"- **{finding.severity.upper()}** `{finding.rule_id}` at `{location}`",
        f"  - Finding: {finding.message}",
        f"  - Fix: {_fix_guidance(finding)}",
    ]
    patch = _suggested_text(finding)
    if patch:
        lines.extend(["  - Suggested runbook text:", "", "```markdown", patch, "```", ""])
    return lines


def _fix_guidance(finding: Finding) -> str:
    path = str(finding.details.get("path") or "")
    action = str(finding.details.get("action") or "")
    guidance = {
        "conflicting-package-managers": "Pick one package manager, name it explicitly, and remove or mark alternatives as fallback-only.",
        "conflicting-commands": "Choose the canonical command for the purpose and document when any fallback command is allowed.",
        "missing-test-command": "Add at least one executable validation command that maintainers and agents can run before final response.",
        "secret-exposure-risk": "Replace concrete secret values with environment variable names or redacted placeholders.",
        "excessive-permission": "Narrow broad permissions and require confirmation for destructive, privileged, network, or sandbox-changing operations.",
        "allow-deny-conflict": f"Resolve the conflicting allow/deny instruction for `{action or 'the affected action'}`.",
        "missing-path": f"Create the referenced path, correct the path, or remove it from the runbook: `{path or 'unknown path'}`.",
        "long-context": "Split long instructions into focused sections or move rarely used details into linked docs.",
        "missing-acceptance-criteria": "Add a clear definition of done, validation steps, and expected final evidence.",
        "missing-locale-hint": "State the expected response language and any localization requirements.",
        "stale-command": "Replace obsolete commands with maintained equivalents and explain migration constraints if legacy commands remain.",
        "vague-delivery": "Replace vague delivery wording with concrete scope, output, and verification expectations.",
    }
    return guidance.get(finding.rule_id, "Clarify the instruction so an agent can execute and verify it safely.")


def _suggested_text(finding: Finding) -> str:
    suggestions = {
        "missing-test-command": "## Validation\n\n- Run `<project test command>` before final response.\n- If a test cannot run locally, explain the blocker and name the closest CI or smoke check.",
        "missing-acceptance-criteria": "## Acceptance Criteria\n\n- The requested change is implemented and scoped to the task.\n- Relevant tests or checks pass.\n- The final response lists changed files, verification evidence, and remaining risks.",
        "missing-locale-hint": "## Response Language\n\n- Reply primarily in Chinese unless the user asks otherwise.\n- Keep code identifiers, commands, and file paths in their original language.",
        "secret-exposure-risk": "## Secrets\n\n- Do not paste real tokens, private keys, passwords, or API keys.\n- Use environment variable names or `<REDACTED>` placeholders in examples.",
        "excessive-permission": "## Permissions\n\n- Ask before destructive file operations, privileged commands, network changes, or sandbox/approval changes.\n- Prefer least-privilege commands and document why elevated access is required.",
        "vague-delivery": "## Deliverable\n\n- State the exact artifact or behavior to change.\n- Include the validation command and expected evidence in the final response.",
    }
    return suggestions.get(finding.rule_id, "")


def _agent_prompt(findings: Iterable[Finding]) -> List[str]:
    top = sorted(findings, key=lambda finding: (-finding.level(), finding.path, finding.line))[:8]
    lines = [
        "## Agent Repair Prompt",
        "",
        "```text",
        "You are improving AI coding agent runbooks for this repository.",
        "Use the findings below as a fix list. Inspect each referenced file before editing.",
        "Fix unsafe, unverifiable, or contradictory instructions first.",
        "",
        "Top findings:",
    ]
    for finding in top:
        lines.append(f"- {finding.severity} {finding.rule_id} at {finding.path}:{finding.line}: {finding.message}")
    lines.extend(
        [
            "",
            "After editing, run `agent-runbook-linter . --check warning` or the repository-specific linter command.",
            "Final response should summarize changed runbook sections, verification evidence, and any accepted residual risk.",
            "```",
            "",
        ]
    )
    return lines


def _sarif_level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"
