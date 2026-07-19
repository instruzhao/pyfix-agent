from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyfixagent.benchmarking.comparison import compare_reports, render_comparison_markdown


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two PyFixAgent benchmark reports.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--allow-protocol-drift",
        action="store_true",
        help="Return success even when benchmark protocol fingerprints differ.",
    )
    parser.add_argument(
        "--allow-unmatched",
        action="store_true",
        help="Return success when one report contains unmatched or zero matched trials.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    comparison = compare_reports(baseline, candidate)
    markdown = render_comparison_markdown(comparison)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output_dir / "comparison.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if not comparison["protocol_compatibility"]["compatible"] and not args.allow_protocol_drift:
        return 2
    if not comparison["comparison_complete"] and not args.allow_unmatched:
        return 3
    return 0


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
