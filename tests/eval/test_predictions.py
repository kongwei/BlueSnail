"""SWE-bench prediction / diff helpers."""

from pathlib import Path

from bluesnail.eval.predictions import extract_unified_diff, make_prediction, resolve_model_patch


SAMPLE_DIFF = """diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,2 +1,2 @@
-old
+new
"""


def test_extract_fenced_diff() -> None:
    text = f"Here is the patch:\n```diff\n{SAMPLE_DIFF}```\nThanks."
    assert extract_unified_diff(text).startswith("diff --git")
    assert "new" in extract_unified_diff(text)


def test_extract_raw_diff() -> None:
    assert extract_unified_diff(SAMPLE_DIFF).startswith("diff --git")


def test_make_prediction_shape() -> None:
    pred = make_prediction("sympy__sympy-20590", "bluesnail", SAMPLE_DIFF)
    assert set(pred) == {"instance_id", "model_name_or_path", "model_patch"}


def test_resolve_patch_prefers_workspace_git(tmp_path: Path) -> None:
    assert resolve_model_patch(tmp_path, SAMPLE_DIFF).startswith("diff --git")
