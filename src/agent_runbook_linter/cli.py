import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .baseline import apply_baseline, load_baseline, render_baseline
from .linter import run_lint
from .reports import write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-runbook-linter",
        description="Lint AI coding agent runbooks and instruction files for CI.",
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root to scan.")
    parser.add_argument("--config", help="JSON or YAML config file.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "junit", "sarif"],
        default="markdown",
        help="Report format.",
    )
    parser.add_argument("--output", help="Write report to this path; parent directories are created.")
    parser.add_argument("--baseline", help="JSON baseline file. Matching findings are suppressed before reporting and --check.")
    parser.add_argument(
        "--check",
        choices=["warning", "error"],
        default=None,
        help="Exit with code 1 when findings at or above this severity exist.",
    )
    parser.add_argument(
        "--write-baseline",
        help="Write a reviewed baseline JSON for current findings instead of a normal report. Use '-' for stdout.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root)
    config_path = Path(args.config) if args.config else None
    output = Path(args.output) if args.output else None

    try:
        result = run_lint(root, config_path)
        if args.write_baseline:
            rendered = render_baseline(result)
            if args.write_baseline == "-":
                sys.stdout.write(rendered)
            else:
                baseline_output = Path(args.write_baseline)
                baseline_output.parent.mkdir(parents=True, exist_ok=True)
                baseline_output.write_text(rendered, encoding="utf-8")
            return 0
        if args.baseline:
            result = apply_baseline(result, load_baseline(Path(args.baseline)))
        rendered = write_report(result, args.format, output)
    except Exception as exc:
        print(f"agent-runbook-linter: {exc}", file=sys.stderr)
        return 2

    if output is None:
        sys.stdout.write(rendered)

    return 1 if result.exceeds(args.check) else 0
