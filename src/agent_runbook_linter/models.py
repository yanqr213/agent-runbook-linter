from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class Document:
    path: Path
    relpath: str
    text: str
    lines: List[str]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    path: str
    line: int = 1
    details: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""

    def level(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 0)


@dataclass
class RuleConfig:
    severity: str = "warning"
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LinterConfig:
    root: Path
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    ignore: List[Dict[str, Any]] = field(default_factory=list)
    rules: Dict[str, RuleConfig] = field(default_factory=dict)
    max_context_lines: int = 220
    default_severity: str = "warning"
    require_locale_hint: bool = True
    locale_terms: List[str] = field(default_factory=list)

    def rule(self, rule_id: str) -> RuleConfig:
        return self.rules.get(rule_id, RuleConfig(severity=self.default_severity))


@dataclass
class LintResult:
    root: Path
    documents: List[Document]
    findings: List[Finding]
    suppressed_findings: List[Finding] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        counts = {"info": 0, "warning": 0, "error": 0}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def suppressed_counts(self) -> Dict[str, int]:
        counts = {"info": 0, "warning": 0, "error": 0}
        for finding in self.suppressed_findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def exceeds(self, threshold: Optional[str]) -> bool:
        if threshold is None:
            return False
        min_level = SEVERITY_ORDER[threshold]
        return any(finding.level() >= min_level for finding in self.findings)
