import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import helpers  # noqa: F401
from agent_runbook_linter.linter import run_lint
from agent_runbook_linter.reports import render_junit, render_json, render_markdown


class ReportsAndCliTests(unittest.TestCase):
    def make_repo(self, text):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "AGENTS.md").write_text(text, encoding="utf-8")
        return root

    def test_json_report_contains_findings(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        payload = json.loads(render_json(result))
        self.assertEqual("agent-runbook-linter", payload["tool"])
        self.assertGreaterEqual(payload["summary"]["findings"], 1)

    def test_markdown_report_contains_location(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        markdown = render_markdown(result)
        self.assertIn("# Agent Runbook Linter Report", markdown)
        self.assertIn("AGENTS.md", markdown)

    def test_junit_report_is_xml(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        xml = render_junit(result)
        root = ElementTree.fromstring(xml)
        self.assertEqual("testsuite", root.tag)

    def test_cli_check_warning_exits_one(self):
        repo = self.make_repo("Language: English.\nAcceptance: done.\n")
        proc = subprocess.run(
            [sys.executable, "-m", "agent_runbook_linter", str(repo), "--check", "warning"],
            cwd=str(helpers.ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(1, proc.returncode)
        self.assertIn("missing-test-command", proc.stdout)

    def test_cli_output_creates_parent_directory(self):
        repo = self.make_repo("Language: English.\nAcceptance: done.\n")
        output = repo / "nested" / "reports" / "runbook.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_runbook_linter",
                str(repo),
                "--format",
                "json",
                "--output",
                str(output),
            ],
            cwd=str(helpers.ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, proc.returncode)
        self.assertEqual("", proc.stdout)
        self.assertTrue(output.exists())
        self.assertIn("findings", json.loads(output.read_text(encoding="utf-8")))

    def test_cli_check_error_respects_severity(self):
        repo = self.make_repo("Language: English.\nAcceptance: done.\n")
        config = repo / "agent-runbook-linter.json"
        config.write_text('{"rules":{"missing-test-command":{"severity":"warning"}}}', encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_runbook_linter",
                str(repo),
                "--config",
                str(config),
                "--check",
                "error",
            ],
            cwd=str(helpers.ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, proc.returncode)


if __name__ == "__main__":
    unittest.main()
