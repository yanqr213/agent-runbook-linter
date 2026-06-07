import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from agent_runbook_linter.linter import run_lint


class RuleTests(unittest.TestCase):
    def lint_text(self, text):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "AGENTS.md").write_text(text, encoding="utf-8")
        return run_lint(root)

    def rule_ids(self, result):
        return {finding.rule_id for finding in result.findings}

    def test_detects_conflicting_package_managers(self):
        result = self.lint_text("Run `npm install` and `pnpm install`.\nRun tests with `npm test`.\nLanguage: English.\nAcceptance: tests pass.\n")
        self.assertIn("conflicting-package-managers", self.rule_ids(result))

    def test_detects_missing_test_command(self):
        result = self.lint_text("Language: English.\nAcceptance: final report is clear.\n")
        self.assertIn("missing-test-command", self.rule_ids(result))

    def test_detects_secret_exposure_risk(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nAPI_KEY=live_secret_value_1234567890\n")
        self.assertIn("secret-exposure-risk", self.rule_ids(result))

    def test_placeholder_secret_is_allowed(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nUse API_KEY=TEST_TOKEN_PLACEHOLDER.\n")
        self.assertNotIn("secret-exposure-risk", self.rule_ids(result))

    def test_detects_excessive_permission(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nAlways use full access and disable sandbox.\n")
        self.assertIn("excessive-permission", self.rule_ids(result))

    def test_detects_allow_deny_conflict(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nAllowed to push.\nNever push.\n")
        self.assertIn("allow-deny-conflict", self.rule_ids(result))

    def test_detects_missing_path(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nRead `docs/runbook.md`.\n")
        self.assertIn("missing-path", self.rule_ids(result))

    def test_existing_path_not_flagged(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "docs").mkdir()
        (root / "docs" / "runbook.md").write_text("ok\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nRead `docs/runbook.md`.\n", encoding="utf-8")
        result = run_lint(root)
        self.assertNotIn("missing-path", self.rule_ids(result))

    def test_detects_long_context(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\n" + ("line\n" * 230))
        self.assertIn("long-context", self.rule_ids(result))

    def test_detects_missing_acceptance_criteria(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\n")
        self.assertIn("missing-acceptance-criteria", self.rule_ids(result))

    def test_detects_missing_locale_hint(self):
        result = self.lint_text("Run tests with `pytest`.\nAcceptance: pass.\n")
        self.assertIn("missing-locale-hint", self.rule_ids(result))

    def test_detects_stale_command_and_vague_delivery(self):
        result = self.lint_text("Run tests with `pytest`.\nLanguage: English.\nAcceptance: pass.\nInstall `npm install -g bower` and make it good.\n")
        ids = self.rule_ids(result)
        self.assertIn("stale-command", ids)
        self.assertIn("vague-delivery", ids)


if __name__ == "__main__":
    unittest.main()
