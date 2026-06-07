# Agent Instructions

Use English for code comments and user-facing summaries unless the request asks for another language. Keep locale-sensitive copy explicit.

## Commands

- Install Python dependencies with `uv sync`.
- Run tests with `uv run python -m unittest discover -s tests`.
- Validate packaging with `uv run python -m build`.

## Safety

- Do not commit, push, delete files, or install global tools without explicit user approval.
- Never print secret values. Use placeholder values such as `TEST_TOKEN_PLACEHOLDER`.

## Acceptance

Work is done when tests pass, the report output is reviewed, and changed files are listed in the final response.
