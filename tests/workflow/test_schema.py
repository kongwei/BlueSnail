"""Workflow schema tests (no Agent runtime)."""

from bluesnail.core.exceptions import WorkflowError
from bluesnail.workflow import (
    Workflow,
    WorkflowBundle,
    WorkflowStep,
    default_direct_workflow,
    default_react_workflow,
    validate_workflow,
)


def test_default_react_workflow_is_valid() -> None:
    workflow = default_react_workflow()
    validate_workflow(workflow)
    assert workflow.entry == "ingest"
    assert any(step.type == "execute_calls" for step in workflow.steps)


def test_invalid_workflow_unknown_step_type() -> None:
    workflow = Workflow(
        id="bad",
        name="bad",
        entry="start",
        steps=[
            WorkflowStep(id="start", type="not_a_type", next="finish"),
            WorkflowStep(id="finish", type="finish"),
        ],
    )
    try:
        validate_workflow(workflow)
    except WorkflowError as exc:
        assert "Unknown step type" in str(exc)
    else:
        raise AssertionError("expected WorkflowError")


def test_bundle_rejects_missing_active() -> None:
    try:
        WorkflowBundle.from_dict(
            {
                "active_id": "missing",
                "workflows": [default_direct_workflow().to_dict()],
            }
        )
    except WorkflowError as exc:
        assert "Active workflow not found" in str(exc)
    else:
        raise AssertionError("expected WorkflowError")


def test_bundle_resolve_by_name() -> None:
    bundle = WorkflowBundle.from_dict(
        {
            "active_id": "react",
            "workflows": [
                default_react_workflow().to_dict(),
                default_direct_workflow().to_dict(),
            ],
        }
    )
    assert bundle.resolve("直接回答").id == "direct"
    assert bundle.resolve("react").id == "react"
