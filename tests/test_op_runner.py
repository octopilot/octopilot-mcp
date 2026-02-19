"""Tests for op_runner — mocks subprocess so no real builds are triggered."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octopilot_mcp.tools.op_runner import _find_op_binary, run_op_build

# ── _find_op_binary ───────────────────────────────────────────────────────────


def test_find_op_binary_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_BINARY", "/custom/bin/op")
    assert _find_op_binary() == "/custom/bin/op"


def test_find_op_binary_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OP_BINARY", raising=False)
    with patch("shutil.which", return_value="/usr/local/bin/op"):
        assert _find_op_binary() == "/usr/local/bin/op"


def test_find_op_binary_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OP_BINARY", raising=False)
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(FileNotFoundError, match="OP_USE_CONTAINER"),
    ):
        _find_op_binary()


# ── OP_USE_CONTAINER env var ──────────────────────────────────────────────────


def test_use_container_mode_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_USE_CONTAINER", "true")
    from octopilot_mcp.tools.op_runner import _use_container_mode

    assert _use_container_mode() is True


def test_use_container_mode_false_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OP_USE_CONTAINER", raising=False)
    from octopilot_mcp.tools.op_runner import _use_container_mode

    assert _use_container_mode() is False


def test_use_container_mode_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    from octopilot_mcp.tools.op_runner import _use_container_mode

    for truthy in ("true", "True", "TRUE", "1", "yes"):
        monkeypatch.setenv("OP_USE_CONTAINER", truthy)
        assert _use_container_mode() is True, f"Expected True for {truthy!r}"

    for falsy in ("false", "0", "no", ""):
        monkeypatch.setenv("OP_USE_CONTAINER", falsy)
        assert _use_container_mode() is False, f"Expected False for {falsy!r}"


def test_run_op_build_respects_op_use_container_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OP_USE_CONTAINER=true causes container mode without use_container=True arg."""
    (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta1\n")
    monkeypatch.setenv("OP_USE_CONTAINER", "true")

    with _mock_subprocess(tmp_path) as mock_run:
        run_op_build(str(tmp_path), "ghcr.io/org")

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "docker"  # container mode was selected


# ── run_op_build ──────────────────────────────────────────────────────────────


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Workspace with a minimal skaffold.yaml."""
    (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta1\n")
    return tmp_path


def _mock_subprocess(workspace: Path, build_result: dict | None = None):
    """Return a context manager that patches subprocess.run and optionally writes build_result.json."""

    def side_effect(*args, **kwargs):
        if build_result is not None:
            (workspace / "build_result.json").write_text(json.dumps(build_result))
        return MagicMock(returncode=0)

    return patch("subprocess.run", side_effect=side_effect)


def test_run_op_build_returns_build_result(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    expected = {"builds": [{"imageName": "my-app", "tag": "ghcr.io/org/my-app:v1@sha256:abc"}]}
    with _mock_subprocess(workspace, expected) as mock_run:
        result = run_op_build(str(workspace), "ghcr.io/org")
    assert result == expected
    # Verify the command contained the right args
    cmd = mock_run.call_args[0][0]
    assert "build" in cmd
    assert "--repo" in cmd
    assert "ghcr.io/org" in cmd


def test_run_op_build_no_build_result_json(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    with _mock_subprocess(workspace, build_result=None):
        result = run_op_build(str(workspace), "ghcr.io/org")
    assert result["status"] == "ok"
    assert "build_result.json not found" in result["note"]


def test_run_op_build_push_flag(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", push=True)
    cmd = mock_run.call_args[0][0]
    assert "--push" in cmd


def test_run_op_build_no_push_flag_by_default(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", push=False)
    cmd = mock_run.call_args[0][0]
    assert "--push" not in cmd


def test_run_op_build_custom_platforms(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", platforms="linux/amd64,linux/arm64")
    cmd = mock_run.call_args[0][0]
    assert "linux/amd64,linux/arm64" in cmd


def test_run_op_build_extra_args(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", extra_args=["--sbom-output", "dist/sbom"])
    cmd = mock_run.call_args[0][0]
    assert "--sbom-output" in cmd
    assert "dist/sbom" in cmd


def test_run_op_build_container_mode(workspace: Path) -> None:
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", use_container=True)
    cmd = mock_run.call_args[0][0]
    # Container mode uses docker, not the op binary directly
    assert cmd[0] == "docker"
    assert "run" in cmd
    assert "ghcr.io/octopilot/op:latest" in cmd


def test_run_op_build_container_mode_custom_image(workspace: Path) -> None:
    with _mock_subprocess(workspace) as mock_run:
        run_op_build(
            str(workspace),
            "ghcr.io/org",
            use_container=True,
            op_image="ghcr.io/octopilot/op:v1.0.0",
        )
    cmd = mock_run.call_args[0][0]
    assert "ghcr.io/octopilot/op:v1.0.0" in cmd


def test_run_op_build_propagates_subprocess_error(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_BINARY", "/usr/bin/op")
    import subprocess

    with (
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "op")),
        pytest.raises(subprocess.CalledProcessError),
    ):
        run_op_build(str(workspace), "ghcr.io/org")
