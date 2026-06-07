import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import LinterConfig, RuleConfig


DEFAULT_INCLUDE = [
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "Codex.md",
    "codex.md",
    "CODEX/CODEX.md",
    "CODEX/codex.md",
    "Codex/CODEX.md",
    ".codex/CODEX.md",
    ".codex/codex.md",
    ".cursor/rules",
    ".cursor/rules/*",
    ".cursor/rules/**/*",
    "README.md",
    "README.*",
]

DEFAULT_EXCLUDE = [
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".venv/**",
    "venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "__pycache__/**",
]

DEFAULT_LOCALE_TERMS = [
    "language",
    "locale",
    "localization",
    "i18n",
    "english",
    "chinese",
    "中文",
    "英文",
    "语言",
    "地区",
    "本地化",
]

DEFAULT_RULE_SEVERITIES = {
    "conflicting-package-managers": "error",
    "conflicting-commands": "error",
    "missing-test-command": "error",
    "secret-exposure-risk": "error",
    "excessive-permission": "error",
    "allow-deny-conflict": "error",
    "missing-path": "warning",
    "long-context": "warning",
    "missing-acceptance-criteria": "warning",
    "missing-locale-hint": "warning",
    "stale-command": "warning",
    "vague-delivery": "warning",
}


def default_config(root: Path) -> LinterConfig:
    return LinterConfig(
        root=root,
        include=list(DEFAULT_INCLUDE),
        exclude=list(DEFAULT_EXCLUDE),
        rules={
            rule_id: RuleConfig(severity=severity)
            for rule_id, severity in DEFAULT_RULE_SEVERITIES.items()
        },
        locale_terms=list(DEFAULT_LOCALE_TERMS),
    )


def discover_config(root: Path) -> Optional[Path]:
    for name in (
        ".agent-runbook-linter.json",
        "agent-runbook-linter.json",
        ".agent-runbook-linter.yaml",
        ".agent-runbook-linter.yml",
    ):
        path = root / name
        if path.exists():
            return path
    return None


def load_config(root: Path, config_path: Optional[Path]) -> LinterConfig:
    config = default_config(root)
    path = config_path or discover_config(root)
    if path is None:
        return config

    raw = _load_raw_config(path)
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain an object: {path}")

    if "include" in raw:
        config.include = _string_list(raw["include"], "include")
    if "exclude" in raw:
        config.exclude = _string_list(raw["exclude"], "exclude")
    if "ignore" in raw:
        if not isinstance(raw["ignore"], list):
            raise ValueError("ignore must be a list")
        config.ignore = [item for item in raw["ignore"] if isinstance(item, dict)]
    if "max_context_lines" in raw:
        config.max_context_lines = int(raw["max_context_lines"])
    if "default_severity" in raw:
        config.default_severity = _severity(raw["default_severity"])
    if "require_locale_hint" in raw:
        config.require_locale_hint = bool(raw["require_locale_hint"])
    if "locale_terms" in raw:
        config.locale_terms = _string_list(raw["locale_terms"], "locale_terms")

    rules = raw.get("rules", {})
    if rules is not None and not isinstance(rules, dict):
        raise ValueError("rules must be an object")
    for rule_id, value in (rules or {}).items():
        current = config.rules.get(rule_id, RuleConfig(severity=config.default_severity))
        if isinstance(value, str):
            current.severity = _severity(value)
        elif isinstance(value, dict):
            if "severity" in value:
                current.severity = _severity(value["severity"])
            if "enabled" in value:
                current.enabled = bool(value["enabled"])
            options = value.get("options")
            if options is not None:
                if not isinstance(options, dict):
                    raise ValueError(f"rules.{rule_id}.options must be an object")
                current.options = dict(options)
        else:
            raise ValueError(f"rules.{rule_id} must be a string or object")
        config.rules[rule_id] = current
    return config


def is_ignored(rule_id: str, path: str, line: int, ignores: Iterable[Dict[str, Any]]) -> bool:
    for item in ignores:
        rules = item.get("rule")
        if rules is not None:
            if isinstance(rules, str):
                rule_values = [rules]
            elif isinstance(rules, list):
                rule_values = [str(value) for value in rules]
            else:
                rule_values = []
            if rule_id not in rule_values and "*" not in rule_values:
                continue
        path_glob = item.get("path")
        if path_glob and not fnmatch.fnmatch(path, str(path_glob)):
            continue
        line_value = item.get("line")
        if line_value is not None:
            try:
                if int(line_value) != line:
                    continue
            except (TypeError, ValueError):
                continue
        return True
    return False


def _load_raw_config(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            return _parse_minimal_yaml(text)
        loaded = yaml.safe_load(text)
        return loaded or {}
    raise ValueError(f"Unsupported config file extension: {path.suffix}")


def _parse_minimal_yaml(text: str) -> Dict[str, Any]:
    """Small dependency-free YAML subset for simple config files."""
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[Any]] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            current_list = None
            if value == "":
                result[key] = []
                current_list = result[key]
            else:
                result[key] = _yaml_scalar(value)
        elif current_key and line.lstrip().startswith("- "):
            if current_list is None:
                if not isinstance(result.get(current_key), list):
                    result[current_key] = []
                current_list = result[current_key]
            current_list.append(_yaml_scalar(line.lstrip()[2:].strip()))
        else:
            raise ValueError("YAML config fallback supports top-level scalars and lists only")
    return result


def _yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _string_list(value: Any, key: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return [str(item) for item in value]


def _severity(value: Any) -> str:
    severity = str(value)
    if severity not in {"info", "warning", "error"}:
        raise ValueError(f"Invalid severity: {severity}")
    return severity
