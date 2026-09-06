"""Agent tool for reading bench evaluation output."""

from __future__ import annotations

from pathlib import Path

from bluesnail.core.schema import build_parameters_schema
from bluesnail.tools.manager import ToolDefinition, ToolManager


def view_bench_output(
    run_id: str = "",
    instance_id: str = "",
    section: str = "summary",
    report_dir: str = "",
) -> str:
    """Read a BlueSnail eval run (summary, patch, trace, or answer)."""
    from bluesnail.eval.view import render_eval_text

    root = Path(report_dir) if report_dir.strip() else Path.cwd()
    instance_ids = [instance_id] if instance_id.strip() else None
    return render_eval_text(
        root,
        run_id=run_id.strip() or None,
        instance_ids=instance_ids,
        section=section.strip() or "summary",
    )


def register_bench_tools(manager: ToolManager) -> None:
    manager.register(
        ToolDefinition(
            name="view_bench_output",
            description=(
                "View BlueSnail SWE-bench evaluation output: run summary, "
                "predictions, instance patch, agent answer, or inference trace. "
                "Artifacts live under <report_dir>/logs/evaluation/<run_id>/."
            ),
            handler=view_bench_output,
            parameters=build_parameters_schema(view_bench_output),
        )
    )
