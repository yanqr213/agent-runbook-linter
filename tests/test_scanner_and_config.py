import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from agent_runbook_linter.config import load_config
from agent_runbook_linter.scanner import discover_documents


class ScannerAndConfigTests(unittest.TestCase):
    def test_discovers_agent_docs_and_agent_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("Run tests with `pytest`.\n", encoding="utf-8")
            (root / "README.md").write_text("Agent runbook: use English.\n", encoding="utf-8")
            (root / "notes.md").write_text("not included\n", encoding="utf-8")
            docs = discover_documents(load_config(root, None))
            self.assertEqual(["AGENTS.md", "README.md"], [doc.relpath for doc in docs])

    def test_readme_without_agent_marker_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Project description only.\n", encoding="utf-8")
            docs = discover_documents(load_config(root, None))
            self.assertEqual([], docs)

    def test_json_config_overrides_rules_and_ignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "agent-runbook-linter.json"
            config_path.write_text(
                json.dumps(
                    {
                        "include": ["AGENTS.md"],
                        "max_context_lines": 10,
                        "rules": {"long-context": {"severity": "error", "enabled": False}},
                        "ignore": [{"rule": "missing-path", "path": "AGENTS.md"}],
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(root, config_path)
            self.assertEqual(["AGENTS.md"], config.include)
            self.assertEqual(10, config.max_context_lines)
            self.assertFalse(config.rules["long-context"].enabled)
            self.assertEqual("error", config.rules["long-context"].severity)
            self.assertEqual("missing-path", config.ignore[0]["rule"])

    def test_yaml_fallback_supports_top_level_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / ".agent-runbook-linter.yml"
            config_path.write_text("include:\n  - AGENTS.md\nmax_context_lines: 12\n", encoding="utf-8")
            config = load_config(root, config_path)
            self.assertEqual(["AGENTS.md"], config.include)
            self.assertEqual(12, config.max_context_lines)


if __name__ == "__main__":
    unittest.main()
