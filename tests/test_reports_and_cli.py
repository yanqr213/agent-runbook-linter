import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import helpers  # noqa: F401
from agent_runbook_linter.baseline import apply_baseline, render_baseline
from agent_runbook_linter.linter import run_lint
from agent_runbook_linter.reports import render_junit, render_json, render_markdown, render_sarif


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
        self.assertIn("fingerprint", payload["findings"][0])

    def test_markdown_report_contains_location(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        markdown = render_markdown(result)
        self.assertIn("# Agent Runbook Linter Report", markdown)
        self.assertIn("AGENTS.md", markdown)
        self.assertIn("Fingerprint", markdown)

    def test_junit_report_is_xml(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        xml = render_junit(result)
        root = ElementTree.fromstring(xml)
        self.assertEqual("testsuite", root.tag)
        self.assertIn("skipped", root.attrib)

    def test_sarif_report_contains_rule_and_location(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        payload = json.loads(render_sarif(result))
        run = payload["runs"][0]
        sarif_result = run["results"][0]

        self.assertEqual("2.1.0", payload["version"])
        self.assertEqual("agent-runbook-linter", run["tool"]["driver"]["name"])
        self.assertEqual("0.3.0", run["tool"]["driver"]["semanticVersion"])
        self.assertEqual("missing-test-command", sarif_result["ruleId"])
        self.assertEqual("error", sarif_result["level"])
        self.assertIn("agentRunbookLinter/v1", sarif_result["partialFingerprints"])
        location = sarif_result["locations"][0]["physicalLocation"]
        self.assertEqual("AGENTS.md", location["artifactLocation"]["uri"])
        self.assertEqual(1, location["region"]["startLine"])

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

    def test_reports_include_suppressed_findings(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        baseline = json.loads(render_baseline(result))
        filtered = apply_baseline(result, {item["fingerprint"] for item in baseline["findings"]})

        self.assertIn("Suppressed By Baseline", render_markdown(filtered))
        self.assertGreaterEqual(json.loads(render_json(filtered))["summary"]["suppressed_findings"], 1)
        junit = ElementTree.fromstring(render_junit(filtered))
        self.assertGreaterEqual(int(junit.attrib["skipped"]), 1)
        sarif = json.loads(render_sarif(filtered))
        self.assertGreaterEqual(sarif["runs"][0]["properties"]["suppressed_findings"], 1)

    def test_cli_baseline_suppresses_known_check_findings(self):
        repo = self.make_repo("Language: English.\nAcceptance: done.\n")
        baseline = repo / "agent-runbook-baseline.json"
        report = repo / "filtered.json"

        write_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_runbook_linter",
                str(repo),
                "--write-baseline",
                str(baseline),
            ],
            cwd=str(helpers.ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, write_proc.returncode)
        self.assertTrue(baseline.exists())

        check_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_runbook_linter",
                str(repo),
                "--baseline",
                str(baseline),
                "--check",
                "warning",
                "--format",
                "json",
                "--output",
                str(report),
            ],
            cwd=str(helpers.ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, check_proc.returncode)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(0, payload["summary"]["findings"])
        self.assertGreaterEqual(payload["summary"]["suppressed_findings"], 1)

    def test_cli_sarif_output_creates_parent_directory(self):
        repo = self.make_repo("Language: English.\nAcceptance: done.\n")
        output = repo / "nested" / "reports" / "runbook.sarif"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_runbook_linter",
                str(repo),
                "--format",
                "sarif",
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
        self.assertEqual("2.1.0", json.loads(output.read_text(encoding="utf-8"))["version"])

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
