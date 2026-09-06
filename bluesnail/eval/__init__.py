"""End-to-end Agent evaluation with a SWE-bench-compatible CLI."""

from bluesnail.eval.dataset import BenchInstance, load_instances, resolve_dataset_name
from bluesnail.eval.predictions import extract_unified_diff, make_prediction
from bluesnail.eval.view import format_eval_run, load_eval_run, render_eval_text

__all__ = [
    "BenchInstance",
    "extract_unified_diff",
    "format_eval_run",
    "load_eval_run",
    "load_instances",
    "main",
    "make_prediction",
    "render_eval_text",
    "resolve_dataset_name",
    "run_evaluation",
]


def __getattr__(name: str):
    if name == "main":
        from bluesnail.eval.cli import main

        return main
    if name == "run_evaluation":
        from bluesnail.eval.runner import run_evaluation

        return run_evaluation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
