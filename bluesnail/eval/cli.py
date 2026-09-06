"""CLI aligned with `python -m swebench.harness.run_evaluation`."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from bluesnail.eval.dataset import load_instances, resolve_dataset_name
from bluesnail.eval.harness import harness_command
from bluesnail.eval.runner import default_agent_factory, run_evaluation


def str2bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in {"yes", "true", "t", "y", "1"}:
        return True
    if lowered in {"no", "false", "f", "n", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "End-to-end BlueSnail Agent evaluation. Flags match SWE-bench "
            "`python -m swebench.harness.run_evaluation` so the same invocation "
            "can generate predictions and optionally score them."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "dataset",
        nargs="?",
        default=None,
        help="Dataset alias (lite, verified, full) or HuggingFace id / local path.",
    )
    parser.add_argument(
        "-d",
        "--dataset_name",
        default="SWE-bench/SWE-bench_Lite",
        help="Name of dataset or path to JSON/JSONL file.",
    )
    parser.add_argument("-s", "--split", default="test", help="Split of the dataset")
    parser.add_argument(
        "-i",
        "--instance_ids",
        nargs="+",
        default=None,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "-p",
        "--predictions_path",
        default=None,
        help="Path to predictions JSONL. Use 'gold' to emit/score gold patches.",
    )
    parser.add_argument(
        "--max_workers",
        "-j",
        type=int,
        default=1,
        help="Maximum number of workers",
    )
    parser.add_argument("--open_file_limit", type=int, default=4096, help="Open file limit")
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=1_800,
        help="Timeout (in seconds) for each instance",
    )
    parser.add_argument(
        "-id",
        "--run_id",
        required=True,
        help="Run ID - identifies the run",
    )
    parser.add_argument(
        "--rewrite_reports",
        type=str2bool,
        default=False,
        help="Forwarded to the SWE-bench harness (re-grade existing outputs).",
    )
    parser.add_argument(
        "--report_dir",
        default=".",
        help="Directory to write reports to",
    )
    parser.add_argument("--modal", type=str2bool, default=False, help="Run harness on Modal")
    parser.add_argument(
        "--gold",
        action="store_true",
        help="Use gold patches (same as --predictions_path gold).",
    )
    parser.add_argument(
        "--harness",
        action="store_true",
        help="After writing predictions, invoke swebench.harness.run_evaluation.",
    )
    parser.add_argument(
        "--harness-only",
        action="store_true",
        help="Skip Agent inference; only run the SWE-bench harness.",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Optional workspace root (uses <root>/<instance_id> when present).",
    )
    parser.add_argument(
        "--model_name_or_path",
        default="bluesnail",
        help="Written into each SWE-bench prediction record.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if not args.run_id:
        raise SystemExit("Run ID must be provided")
    if args.dataset:
        args.dataset_name = resolve_dataset_name(args.dataset)
    else:
        args.dataset_name = resolve_dataset_name(args.dataset_name)
    gold = args.gold or (args.predictions_path == "gold")
    args.gold = gold
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = _resolve_predictions_path(args, report_dir)

    if not args.harness_only:
        instances = load_instances(
            args.dataset_name,
            split=args.split,
            instance_ids=args.instance_ids,
        )
        summary = run_evaluation(
            instances,
            run_id=args.run_id,
            report_dir=report_dir,
            predictions_path=predictions_path,
            model_name_or_path=args.model_name_or_path,
            agent_factory=default_agent_factory,
            gold=args.gold,
            timeout=args.timeout,
            max_workers=args.max_workers,
            workspace_root=Path(args.workspace) if args.workspace else None,
        )
        print(
            f"Wrote {summary['instances_submitted']} predictions to {predictions_path}"
        )
        print(f"Report: {report_dir / 'logs' / 'evaluation' / args.run_id / 'results.json'}")

    if args.harness or args.harness_only:
        harness_preds = "gold" if args.gold else str(predictions_path)
        command = harness_command(
            dataset_name=args.dataset_name,
            split=args.split,
            predictions_path=harness_preds,
            run_id=args.run_id,
            max_workers=args.max_workers,
            timeout=args.timeout,
            report_dir=str(report_dir),
            instance_ids=args.instance_ids,
            rewrite_reports=args.rewrite_reports,
            modal=args.modal,
            open_file_limit=args.open_file_limit,
        )
        print("Running SWE-bench harness:\n  " + " ".join(command))
        completed = subprocess.run(command, check=False)
        return completed.returncode
    return 0


def _resolve_predictions_path(args: argparse.Namespace, report_dir: Path) -> Path:
    if args.predictions_path and args.predictions_path != "gold":
        return Path(args.predictions_path)
    return report_dir / "logs" / "evaluation" / args.run_id / "preds.jsonl"


if __name__ == "__main__":
    raise SystemExit(main())
