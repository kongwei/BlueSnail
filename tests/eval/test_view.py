"""Inspect saved bench evaluation output."""

from pathlib import Path

from bluesnail.core.types import LLMResponse
from bluesnail.eval.dataset import BenchInstance
from bluesnail.eval.runner import run_evaluation
from bluesnail.eval.view import format_eval_run, list_run_ids, load_eval_run, render_eval_text
from bluesnail.integration import Agent, AgentConfig, MockLLMProvider
from bluesnail.service import AgentService

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("bug")
+print("fixed")
"""


def _factory(_workspace: Path | None) -> AgentService:
    llm = MockLLMProvider(responses=[LLMResponse(content=f"```diff\n{DIFF}```", finish_reason="stop")])
    return AgentService(Agent(llm=llm, config=AgentConfig()))


def _run(tmp_path: Path) -> Path:
    instances = [
        BenchInstance(instance_id="demo__repo-1", problem_statement="Fix the crash"),
    ]
    run_evaluation(
        instances,
        run_id="view-run",
        report_dir=tmp_path,
        predictions_path=tmp_path / "preds.jsonl",
        model_name_or_path="bluesnail",
        agent_factory=_factory,
        max_workers=1,
    )
    return tmp_path


def test_list_and_load_eval_run(tmp_path: Path) -> None:
    _run(tmp_path)
    assert list_run_ids(tmp_path) == ["view-run"]
    run = load_eval_run(tmp_path, "view-run")
    assert run.instances[0].instance_id == "demo__repo-1"
    assert "diff --git" in run.instances[0].patch
    summary = format_eval_run(run, section="summary")
    assert "view-run" in summary
    assert "demo__repo-1" in summary
    patch_text = render_eval_text(
        tmp_path,
        run_id="view-run",
        instance_ids=["demo__repo-1"],
        section="patch",
    )
    assert "print(\"fixed\")" in patch_text
    trace_text = render_eval_text(tmp_path, run_id="view-run", section="trace")
    assert "workflow" in trace_text or "start" in trace_text


def test_show_cli_prints_summary(tmp_path: Path, capsys) -> None:
    _run(tmp_path)
    from bluesnail.eval.cli import main

    code = main(["show", "--run_id", "view-run", "--report_dir", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert "view-run" in captured.out
    assert "demo__repo-1" in captured.out
