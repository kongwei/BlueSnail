"""CLI for `bluesnail-eval show`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bluesnail.eval.view import SECTIONS, format_eval_run, list_run_ids, load_eval_run


def build_show_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bluesnail-eval show",
        description="View BlueSnail bench evaluation output (summary, patch, trace).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-id",
        "--run_id",
        default=None,
        help="Run ID under <report_dir>/logs/evaluation/<run_id>",
    )
    parser.add_argument(
        "--report_dir",
        default=".",
        help="Directory that contains logs/evaluation",
    )
    parser.add_argument(
        "-i",
        "--instance_ids",
        nargs="+",
        default=None,
        help="Instance IDs to show (space separated)",
    )
    parser.add_argument(
        "--section",
        default="summary",
        choices=SECTIONS,
        help="Which part of the run to print",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="List known eval run IDs and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable JSON instead of text",
    )
    return parser


def show_main(argv: list[str] | None = None) -> int:
    args = build_show_parser().parse_args(argv)
    report_dir = Path(args.report_dir)
    if args.list_runs or (args.run_id is None and not _single_run_available(report_dir)):
        runs = list_run_ids(report_dir)
        if args.list_runs:
            if not runs:
                print(f"No eval runs under {report_dir / 'logs' / 'evaluation'}")
                return 0
            print("\n".join(runs))
            return 0
        if not runs:
            print(f"No eval runs under {report_dir / 'logs' / 'evaluation'}", file=sys.stderr)
            return 1
        print(
            "Multiple eval runs found; pass --run_id. Runs:\n  " + "\n  ".join(runs),
            file=sys.stderr,
        )
        return 1
    try:
        run = load_eval_run(report_dir, args.run_id)
        if args.as_json:
            payload = run.to_dict()
            if args.instance_ids:
                wanted = set(args.instance_ids)
                payload["instances"] = [
                    item for item in payload["instances"] if item["instance_id"] in wanted
                ]
                payload["predictions"] = [
                    item for item in payload["predictions"] if item.get("instance_id") in wanted
                ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(
            format_eval_run(
                run,
                instance_ids=args.instance_ids,
                section=args.section,
            ),
            end="",
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _single_run_available(report_dir: Path) -> bool:
    return len(list_run_ids(report_dir)) == 1
