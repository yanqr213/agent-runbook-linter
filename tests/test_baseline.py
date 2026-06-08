import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from agent_runbook_linter.baseline import apply_baseline, load_baseline, render_baseline
from agent_runbook_linter.linter import run_lint


class BaselineTests(unittest.TestCase):
    def make_repo(self, text: str) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "AGENTS.md").write_text(text, encoding="utf-8")
        return root

    def test_render_baseline_contains_fingerprints(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        data = json.loads(render_baseline(result))

        self.assertEqual(1, data["schema_version"])
        self.assertGreaterEqual(data["finding_count"], 1)
        self.assertTrue(data["findings"][0]["fingerprint"])

    def test_apply_baseline_suppresses_known_findings(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        data = json.loads(render_baseline(result))
        filtered = apply_baseline(result, {item["fingerprint"] for item in data["findings"]})

        self.assertEqual([], filtered.findings)
        self.assertGreaterEqual(len(filtered.suppressed_findings), 1)
        self.assertFalse(filtered.exceeds("warning"))

    def test_load_baseline_accepts_object_shape(self):
        result = run_lint(self.make_repo("Language: English.\nAcceptance: done.\n"))
        root = Path(result.root)
        baseline = root / "baseline.json"
        baseline.write_text(render_baseline(result), encoding="utf-8")

        self.assertGreaterEqual(len(load_baseline(baseline)), 1)


if __name__ == "__main__":
    unittest.main()
