"""Eval runner writes SWE-bench JSONL and inference traces."""

from pathlib import Path

from bluesnail.core.types import LLMResponse
from bluesnail.eval.dataset import BenchInstance
from bluesnail.eval.runner import run_evaluation
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


def test_run_evaluation_writes_preds_and_traces(tmp_path: Path) -> None:
    instances = [
        BenchInstance(instance_id="demo__repo-1", problem_statement="Fix the crash"),
    ]
    preds = tmp_path / "preds.jsonl"
    summary = run_evaluation(
        instances,
        run_id="unit-run",
        report_dir=tmp_path,
        predictions_path=preds,
        model_name_or_path="bluesnail",
        agent_factory=_factory,
        max_workers=1,
    )
    text = preds.read_text(encoding="utf-8")
    assert "demo__repo-1" in text
    assert "model_patch" in text
    assert "diff --git" in text
    trace = tmp_path / "logs" / "evaluation" / "unit-run" / "demo__repo-1" / "trace.jsonl"
    assert trace.is_file()
    assert "workflow" in trace.read_text(encoding="utf-8")
    assert summary["instances_submitted"] == 1
    assert summary["instances_with_empty_patches"] == []


def test_gold_predictions_skip_agent(tmp_path: Path) -> None:
    instances = [
        BenchInstance(instance_id="gold-1", problem_statement="issue", patch=DIFF),
    ]
    preds = tmp_path / "gold.jsonl"

    def boom(_workspace: Path | None) -> AgentService:
        raise AssertionError("agent should not run for gold predictions")

    summary = run_evaluation(
        instances,
        run_id="gold-run",
        report_dir=tmp_path,
        predictions_path=preds,
        model_name_or_path="gold",
        agent_factory=boom,
        gold=True,
    )
    assert "diff --git" in preds.read_text(encoding="utf-8")
    assert summary["instances_submitted"] == 1
