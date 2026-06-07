# Contributing

Thanks for helping improve `agent-runbook-linter`.

## Development setup

```bash
python -m pip install -e .
python -m unittest discover -s tests
```

## Adding a rule

1. Add a rule function in `src/agent_runbook_linter/rules.py`.
2. Register it with `@rule("new-rule-id")`.
3. Add the default severity in `src/agent_runbook_linter/config.py`.
4. Add focused tests under `tests/`.
5. Document the rule in `README.md`.

## Contribution guidelines

- Keep runtime dependencies minimal.
- Prefer readable, deterministic static analysis over clever parsing.
- Do not add real tokens, passwords, personal emails, or live service credentials to examples or tests.
- Use `.test` domains in examples when a domain is needed.
- Keep CLI output stable enough for CI consumers.
