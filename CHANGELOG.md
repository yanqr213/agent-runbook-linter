# Changelog

All notable changes to this project will be documented in this file.

## 0.3.0 - 2026-06-08

- Added reviewed baseline JSON output for known runbook findings.
- Added `--baseline` filtering and `--write-baseline` CLI support.
- Added stable finding fingerprints to JSON, Markdown, JUnit, and SARIF outputs.
- Added CI smoke coverage for baseline generation and filtered checks.

## 0.2.0 - 2026-06-08

- Added SARIF 2.1.0 output for GitHub Code Scanning.
- Added SARIF report and CLI output tests.
- Added SARIF CI smoke coverage.
- Added public GitHub project URLs.

## 0.1.0 - 2026-06-08

- Initial release of the offline `agent-runbook-linter` CLI.
- Added discovery for agent instruction files and agent-related README content.
- Added Markdown, JSON, and JUnit reports.
- Added JSON config, optional YAML config fallback, ignore rules, severities, and CI check thresholds.
- Added rules for command conflicts, missing tests, secret risks, excessive permissions, allow/deny conflicts, missing paths, long context, missing acceptance criteria, missing locale hints, stale commands, and vague delivery.
