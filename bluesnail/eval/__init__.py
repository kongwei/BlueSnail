"""End-to-end Agent evaluation with a SWE-bench-compatible CLI."""

from bluesnail.eval.cli import main
from bluesnail.eval.dataset import BenchInstance, load_instances, resolve_dataset_name
from bluesnail.eval.predictions import extract_unified_diff, make_prediction
from bluesnail.eval.runner import run_evaluation

__all__ = [
    "BenchInstance",
    "extract_unified_diff",
    "load_instances",
    "main",
    "make_prediction",
    "resolve_dataset_name",
    "run_evaluation",
]
