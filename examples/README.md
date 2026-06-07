# examples

This directory contains small repositories and configuration files that can be
linted directly from a checkout.

Run from the project root:

```bash
python -m agent_runbook_linter examples/healthy-repo --format markdown
python -m agent_runbook_linter examples/problem-repo --format json --config examples/rules.json
```
