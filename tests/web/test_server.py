"""Tests for WebUI server startup options."""

import os
import sys
from pathlib import Path

from bluesnail.web.server import configure_filesystem_workspace


def test_configure_filesystem_workspace_uses_explicit_path(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    configured = configure_filesystem_workspace(workspace)
    assert configured == workspace.resolve()
    assert os.environ["BLUESNAIL_WORKSPACE"] == str(workspace.resolve())


def test_configure_filesystem_workspace_defaults_to_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    configured = configure_filesystem_workspace(None)
    assert configured == tmp_path.resolve()
    assert os.environ["BLUESNAIL_WORKSPACE"] == str(tmp_path.resolve())


def test_main_sets_workspace_from_cli(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "cli-root"
    workspace.mkdir()
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bluesnail-web",
            "--workspace",
            str(workspace),
            "--no-reload",
        ],
    )

    from bluesnail.web.server import main

    main()
    assert os.environ["BLUESNAIL_WORKSPACE"] == str(workspace.resolve())
