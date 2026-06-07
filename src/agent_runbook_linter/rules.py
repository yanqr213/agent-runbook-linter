import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Match, Sequence, Set, Tuple

from .config import is_ignored
from .models import Document, Finding, LinterConfig


RuleFn = Callable[[Sequence[Document], LinterConfig], Iterable[Finding]]


PACKAGE_MANAGER_COMMANDS = {
    "npm": re.compile(r"\bnpm\s+(?:install|ci|test|run|exec|start|build)\b", re.I),
    "pnpm": re.compile(r"\bpnpm\s+(?:install|test|run|exec|start|build)\b", re.I),
    "yarn": re.compile(r"\byarn\s+(?:install|test|run|start|build|add)\b", re.I),
    "bun": re.compile(r"\bbun\s+(?:install|test|run|x)\b", re.I),
    "pip": re.compile(r"\bpip(?:3)?\s+install\b", re.I),
    "poetry": re.compile(r"\bpoetry\s+(?:install|run|add)\b", re.I),
    "uv": re.compile(r"\buv\s+(?:pip|sync|run|add)\b", re.I),
}

TEST_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"\bnpm\s+(?:test|run\s+test)\b",
        r"\bpnpm\s+(?:test|run\s+test)\b",
        r"\byarn\s+(?:test|run\s+test)\b",
        r"\bbun\s+test\b",
        r"\bpytest\b",
        r"\bpython\s+-m\s+unittest\b",
        r"\bgo\s+test\b",
        r"\bcargo\s+test\b",
        r"\bmvn\s+test\b",
        r"\bgradle\s+test\b",
        r"\bdotnet\s+test\b",
    ]
]

SECRET_PATTERNS = [
    re.compile(r"\b(?:[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASS|API_KEY)|API_KEY)\s*=\s*['\"]?[^'\"\s`]+", re.I),
    re.compile(r"\b(?:sk|pk)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),
]

OVER_PERMISSION_PATTERNS = [
    re.compile(r"\b(?:always|never ask|without asking|无需确认|不用确认).{0,80}\b(?:sudo|admin|administrator|root|chmod\s+777|rm\s+-rf)\b", re.I),
    re.compile(r"\b(?:full access|unrestricted|danger-full-access|所有权限|完全权限)\b", re.I),
    re.compile(r"\b(?:disable|turn off).{0,50}\b(?:sandbox|approval|permission)\b", re.I),
]

STALE_COMMAND_PATTERNS = [
    re.compile(r"\bpython2\b", re.I),
    re.compile(r"\bpip\s+install\s+--upgrade\s+pip==9\.", re.I),
    re.compile(r"\bnpm\s+install\s+-g\s+bower\b", re.I),
    re.compile(r"\bapt-key\s+add\b", re.I),
    re.compile(r"\b(?:tslint|node-sass)\b", re.I),
]

ALLOW_DENY_VERBS = {
    "delete": [r"delete", r"remove", r"rm\s+-rf", r"删除"],
    "commit": [r"commit", r"git\s+commit", r"提交"],
    "push": [r"push", r"git\s+push", r"推送"],
    "install": [r"install", r"安装"],
    "network": [r"network", r"internet", r"联网", r"网络"],
}

ACCEPTANCE_TERMS = [
    "acceptance",
    "done when",
    "definition of done",
    "verify",
    "validation",
    "expected output",
    "验收",
    "完成标准",
    "验证",
    "预期输出",
]

VAGUE_DELIVERY_PATTERNS = [
    re.compile(r"\b(?:do your best|make it good|clean up|improve it|ship it|finish it)\b", re.I),
    re.compile(r"(尽量|随便|看着办|完善一下|优化一下|交付即可)"),
]

RULES: Dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    def decorator(fn: RuleFn) -> RuleFn:
        RULES[rule_id] = fn
        return fn

    return decorator


def lint_documents(documents: Sequence[Document], config: LinterConfig) -> List[Finding]:
    findings: List[Finding] = []
    for rule_id, fn in RULES.items():
        rule_config = config.rule(rule_id)
        if not rule_config.enabled:
            continue
        for finding in fn(documents, config):
            severity = rule_config.severity
            adjusted = Finding(
                rule_id=finding.rule_id,
                severity=severity,
                message=finding.message,
                path=finding.path,
                line=finding.line,
                details=finding.details,
            )
            if not is_ignored(adjusted.rule_id, adjusted.path, adjusted.line, config.ignore):
                findings.append(adjusted)
    findings.sort(key=lambda item: (item.path, item.line, item.rule_id))
    return findings


@rule("conflicting-package-managers")
def conflicting_package_managers(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    seen: Dict[str, List[Tuple[str, int]]] = {}
    for doc in documents:
        for name, regex in PACKAGE_MANAGER_COMMANDS.items():
            for line_no, _line in _matches(doc, regex):
                seen.setdefault(name, []).append((doc.relpath, line_no))
    js = [name for name in ("npm", "pnpm", "yarn", "bun") if name in seen]
    py = [name for name in ("pip", "poetry", "uv") if name in seen]
    for group in (js, py):
        if len(group) > 1:
            first_path, first_line = seen[group[0]][0]
            yield Finding(
                "conflicting-package-managers",
                "warning",
                f"Multiple package managers are instructed: {', '.join(group)}.",
                first_path,
                first_line,
                {"package_managers": group},
            )


@rule("conflicting-commands")
def conflicting_commands(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    command_lines: Dict[str, Set[str]] = {}
    locations: Dict[str, Tuple[str, int]] = {}
    for doc in documents:
        for line_no, line in enumerate(doc.lines, 1):
            lower = line.lower()
            if "test" in lower:
                for match in re.finditer(r"\b(?:npm|pnpm|yarn|bun|pytest|go|cargo|mvn|gradle|dotnet)\b[^\n`]*", line, re.I):
                    command = _normalize_command(match.group(0))
                    command_lines.setdefault("test", set()).add(command)
                    locations.setdefault("test", (doc.relpath, line_no))
            if "build" in lower:
                for match in re.finditer(r"\b(?:npm|pnpm|yarn|bun|make|cargo|mvn|gradle|dotnet)\b[^\n`]*", line, re.I):
                    command = _normalize_command(match.group(0))
                    command_lines.setdefault("build", set()).add(command)
                    locations.setdefault("build", (doc.relpath, line_no))
    for purpose, commands in command_lines.items():
        meaningful = {command for command in commands if len(command) > 2}
        if len(meaningful) > 2:
            path, line = locations[purpose]
            yield Finding(
                "conflicting-commands",
                "warning",
                f"Several {purpose} commands are listed without precedence: {', '.join(sorted(meaningful)[:4])}.",
                path,
                line,
                {"purpose": purpose, "commands": sorted(meaningful)},
            )


@rule("missing-test-command")
def missing_test_command(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    if not documents:
        return
    text = "\n".join(doc.text for doc in documents)
    if not any(regex.search(text) for regex in TEST_PATTERNS):
        first = documents[0]
        yield Finding(
            "missing-test-command",
            "warning",
            "No executable test command was found in agent instructions.",
            first.relpath,
            1,
        )


@rule("secret-exposure-risk")
def secret_exposure_risk(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        for regex in SECRET_PATTERNS:
            for line_no, line in _matches(doc, regex):
                if _is_placeholder_secret(line):
                    continue
                yield Finding(
                    "secret-exposure-risk",
                    "warning",
                    "Instruction appears to expose or request a concrete secret value.",
                    doc.relpath,
                    line_no,
                )


@rule("excessive-permission")
def excessive_permission(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        for regex in OVER_PERMISSION_PATTERNS:
            for line_no, _line in _matches(doc, regex):
                yield Finding(
                    "excessive-permission",
                    "warning",
                    "Instruction grants broad permissions or bypasses approval/sandbox controls.",
                    doc.relpath,
                    line_no,
                )


@rule("allow-deny-conflict")
def allow_deny_conflict(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    allow: Dict[str, Tuple[str, int]] = {}
    deny: Dict[str, Tuple[str, int]] = {}
    for doc in documents:
        for line_no, line in enumerate(doc.lines, 1):
            lower = line.lower()
            for action, terms in ALLOW_DENY_VERBS.items():
                if any(re.search(term, lower, re.I) for term in terms):
                    if _contains_allow(lower):
                        allow.setdefault(action, (doc.relpath, line_no))
                    if _contains_deny(lower):
                        deny.setdefault(action, (doc.relpath, line_no))
    for action in sorted(set(allow).intersection(deny)):
        path, line = deny[action]
        yield Finding(
            "allow-deny-conflict",
            "warning",
            f"Instructions both allow and forbid action: {action}.",
            path,
            line,
            {"action": action},
        )


@rule("missing-path")
def missing_path(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        for line_no, line in enumerate(doc.lines, 1):
            for token in _path_tokens(line):
                if _should_skip_path(token):
                    continue
                candidate = (config.root / token).resolve()
                try:
                    candidate.relative_to(config.root.resolve())
                except ValueError:
                    continue
                if not candidate.exists():
                    yield Finding(
                        "missing-path",
                        "warning",
                        f"Referenced path does not exist: {token}",
                        doc.relpath,
                        line_no,
                        {"path": token},
                    )


@rule("long-context")
def long_context(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        if len(doc.lines) > config.max_context_lines:
            yield Finding(
                "long-context",
                "warning",
                f"Instruction document has {len(doc.lines)} lines, above limit {config.max_context_lines}.",
                doc.relpath,
                config.max_context_lines + 1,
                {"lines": len(doc.lines), "limit": config.max_context_lines},
            )


@rule("missing-acceptance-criteria")
def missing_acceptance_criteria(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    if not documents:
        return
    combined = "\n".join(doc.text.lower() for doc in documents)
    if not any(term in combined for term in ACCEPTANCE_TERMS):
        first = documents[0]
        yield Finding(
            "missing-acceptance-criteria",
            "warning",
            "No acceptance criteria, validation command, or expected output guidance was found.",
            first.relpath,
            1,
        )


@rule("missing-locale-hint")
def missing_locale_hint(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    if not config.require_locale_hint or not documents:
        return
    combined = "\n".join(doc.text.lower() for doc in documents)
    if not any(term.lower() in combined for term in config.locale_terms):
        first = documents[0]
        yield Finding(
            "missing-locale-hint",
            "warning",
            "No language, locale, or localization guidance was found for agent responses.",
            first.relpath,
            1,
        )


@rule("stale-command")
def stale_command(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        for regex in STALE_COMMAND_PATTERNS:
            for line_no, _line in _matches(doc, regex):
                yield Finding(
                    "stale-command",
                    "warning",
                    "Instruction references a command or tool that is commonly obsolete.",
                    doc.relpath,
                    line_no,
                )


@rule("vague-delivery")
def vague_delivery(documents: Sequence[Document], config: LinterConfig) -> Iterable[Finding]:
    for doc in documents:
        for regex in VAGUE_DELIVERY_PATTERNS:
            for line_no, _line in _matches(doc, regex):
                yield Finding(
                    "vague-delivery",
                    "warning",
                    "Delivery instruction is vague and may be hard for an agent to execute or verify.",
                    doc.relpath,
                    line_no,
                )


def _matches(doc: Document, regex: re.Pattern[str]) -> Iterable[Tuple[int, str]]:
    for line_no, line in enumerate(doc.lines, 1):
        if regex.search(line):
            yield line_no, line


def _normalize_command(command: str) -> str:
    command = re.sub(r"\s+", " ", command.strip(" .,:;`"))
    command = re.sub(r"\s+(?:and|or|then|&&|\|\|).*$", "", command, flags=re.I)
    return command[:80]


def _is_placeholder_secret(line: str) -> bool:
    lower = line.lower()
    placeholders = ["replace", "placeholder", "dummy", "redacted", "not-a-secret", "test-token", "sample"]
    return any(word in lower for word in placeholders)


def _contains_allow(line: str) -> bool:
    return bool(re.search(r"\b(?:allow|allowed|may|can|permit|permitted|允许|可以)\b", line, re.I))


def _contains_deny(line: str) -> bool:
    return bool(re.search(r"\b(?:deny|denied|must not|never|forbid|forbidden|prohibit|禁止|不得|不要)\b", line, re.I))


def _path_tokens(line: str) -> Iterable[str]:
    candidates = re.findall(r"(?:`([^`]+)`|\b((?:\.?/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+))", line)
    for quoted, bare in candidates:
        token = (quoted or bare).strip()
        if token:
            yield token.replace("\\", "/")


def _should_skip_path(token: str) -> bool:
    if token.startswith(("http://", "https://", "mailto:")):
        return True
    if token.startswith(("$", "~", "/")):
        return True
    if ".." in Path(token).parts:
        return True
    if re.search(r"\s", token):
        return True
    if "/" not in token and "\\" not in token:
        return True
    if re.match(r"^[A-Z_]+=", token):
        return True
    return False
