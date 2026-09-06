"""Bench output viewer tool."""

from pathlib import Path

from bluesnail.core.types import LLMResponse, ToolCall
from bluesnail.eval.dataset import BenchInstance
from bluesnail.eval.runner import run_evaluation
from bluesnail.integration import Agent, AgentConfig, MockLLMProvider
from bluesnail.service import AgentService
from bluesnail.tools import create_default_tools


DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("bug")
+print("fixed")
"""


def test_create_default_tools_registers_view_bench_output() -> None:
    names = {tool.name for tool in create_default_tools().registry.list_tools()}
    assert "view_bench_output" in names


def test_view_bench_output_tool_reads_run(tmp_path: Path) -> None:
    llm = MockLLMProvider(responses=[LLMResponse(content=f"```diff\n{DIFF}```", finish_reason="stop")])
    service = AgentService(Agent(llm=llm, config=AgentConfig()))
    run_evaluation(
        [BenchInstance(instance_id="demo__repo-1", problem_statement="Fix the crash")],
        run_id="tool-run",
        report_dir=tmp_path,
        predictions_path=tmp_path / "preds.jsonl",
        model_name_or_path="bluesnail",
        agent_factory=lambda _workspace: service,
        max_workers=1,
    )
    tools = create_default_tools()
    result = tools.run(
        ToolCall(
            id="call_1",
            name="view_bench_output",
            arguments={
                "run_id": "tool-run",
                "report_dir": str(tmp_path),
                "section": "patch",
                "instance_id": "demo__repo-1",
            },
        )
    )
    assert not result.is_error
    assert "demo__repo-1" in result.content
    assert "diff --git" in result.content
