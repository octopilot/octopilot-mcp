"""Tests for op_runner — mocks subprocess so no real builds are triggered."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octopilot_mcp.tools.op_runner import _assert_docker_available, _get_op_image, run_op_build

# ── _assert_docker_available ──────────────────────────────────────────────────


def test_assert_docker_available_passes_when_docker_found() -> None:
    with patch("shutil.which", return_value="/usr/bin/docker"):
        _assert_docker_available()  # should not raise


def test_assert_docker_available_raises_with_instructions() -> None:
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="Docker is not available"),
    ):
        _assert_docker_available()


def test_assert_docker_error_mentions_colima() -> None:
    with patch("shutil.which", return_value=None), pytest.raises(RuntimeError) as exc_info:
        _assert_docker_available()
    assert "Colima" in str(exc_info.value)


# ── _get_op_image ─────────────────────────────────────────────────────────────


def test_get_op_image_default() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("OP_IMAGE", None)
        assert _get_op_image() == "ghcr.io/octopilot/op:latest"


def test_get_op_image_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_IMAGE", "ghcr.io/octopilot/op:v1.0.0")
    assert _get_op_image() == "ghcr.io/octopilot/op:v1.0.0"


# ── run_op_build ──────────────────────────────────────────────────────────────


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Workspace with a minimal skaffold.yaml."""
    (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta1\n")
    return tmp_path


def _mock_run(workspace: Path, build_result: dict | None = None):
    """Patch subprocess.run and docker check; optionally write build_result.json."""

    def side_effect(*args, **kwargs):
        if build_result is not None:
            (workspace / "build_result.json").write_text(json.dumps(build_result))
        return MagicMock(returncode=0)

    return patch("subprocess.run", side_effect=side_effect)


def _with_docker():
    """Patch shutil.which to report Docker is available."""
    return patch("shutil.which", return_value="/usr/bin/docker")


def test_run_op_build_always_uses_docker(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "docker"


def test_run_op_build_uses_pull_always(workspace: Path) -> None:
    """--pull always ensures the latest image is used on every invocation."""
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    cmd = mock_run.call_args[0][0]
    assert "--pull" in cmd
    pull_idx = cmd.index("--pull")
    assert cmd[pull_idx + 1] == "always"


def test_run_op_build_returns_build_result(workspace: Path) -> None:
    expected = {"builds": [{"imageName": "my-app", "tag": "ghcr.io/org/my-app:v1@sha256:abc"}]}
    with _with_docker(), _mock_run(workspace, expected):
        result = run_op_build(str(workspace), "ghcr.io/org")
    assert result == expected


def test_run_op_build_no_build_result_json(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace, build_result=None):
        result = run_op_build(str(workspace), "ghcr.io/org")
    assert result["status"] == "ok"
    assert "build_result.json not found" in result["note"]


def _shell_cmd(mock_run) -> str:
    """Extract the shell command string passed to /bin/sh -c."""
    return mock_run.call_args[0][0][-1]


def test_run_op_build_push_flag(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", push=True)
    assert "--push" in _shell_cmd(mock_run)


def test_run_op_build_no_push_by_default(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", push=False)
    assert "--push" not in _shell_cmd(mock_run)


def test_run_op_build_custom_platforms(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", platforms="linux/amd64,linux/arm64")
    assert "linux/amd64,linux/arm64" in _shell_cmd(mock_run)


def test_run_op_build_custom_registry_in_cmd(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "europe-west1-docker.pkg.dev/myproject/myrepo")
    assert "europe-west1-docker.pkg.dev/myproject/myrepo" in _shell_cmd(mock_run)


def test_run_op_build_uses_default_image(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")
    cmd = mock_run.call_args[0][0]
    assert "ghcr.io/octopilot/op:latest" in cmd


def test_run_op_build_custom_op_image(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", op_image="ghcr.io/octopilot/op:v1.0.0")
    cmd = mock_run.call_args[0][0]
    assert "ghcr.io/octopilot/op:v1.0.0" in cmd
    assert "ghcr.io/octopilot/op:latest" not in cmd


def test_run_op_build_op_image_from_env(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_IMAGE", "ghcr.io/octopilot/op:v0.9.0")
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")
    cmd = mock_run.call_args[0][0]
    assert "ghcr.io/octopilot/op:v0.9.0" in cmd


def test_run_op_build_extra_args(workspace: Path) -> None:
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org", extra_args=["--sbom-output", "dist/sbom"])
    shell = _shell_cmd(mock_run)
    assert "--sbom-output" in shell
    assert "dist/sbom" in shell


def test_run_op_build_fails_when_docker_missing(workspace: Path) -> None:
    with patch("shutil.which", return_value=None), pytest.raises(RuntimeError, match="Docker"):
        run_op_build(str(workspace), "ghcr.io/org")


def test_run_op_build_propagates_subprocess_error(workspace: Path) -> None:
    with (
        _with_docker(),
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker")),
        pytest.raises(subprocess.CalledProcessError),
    ):
        run_op_build(str(workspace), "ghcr.io/org")


def test_run_op_build_mounts_workspace(workspace: Path) -> None:
    """The workspace is mounted into the container at /workspace."""
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")
    cmd = mock_run.call_args[0][0]
    workspace_str = str(workspace.resolve())
    assert any(workspace_str in arg for arg in cmd)
    assert "-w" in cmd


# ── Output handling — never swallow, never corrupt MCP protocol ───────────────


def test_run_op_build_routes_stdout_to_stderr(workspace: Path) -> None:
    """
    stdout must be routed to sys.stderr, not left as None and not captured.

    When the MCP server uses stdio transport (Cursor, Claude Desktop),
    the process stdout IS the MCP wire protocol.  Subprocess output sent
    there corrupts the JSON-RPC stream silently.  This test pins the
    contract: stdout always goes to sys.stderr.
    """
    import sys

    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("stdout") is sys.stderr, (
        "stdout must be sys.stderr — never None (inherits proto wire) or PIPE (swallows output)"
    )


def test_run_op_build_routes_stderr_to_stderr(workspace: Path) -> None:
    """stderr must also be routed to sys.stderr so build errors are visible."""
    import sys

    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("stderr") is sys.stderr, (
        "stderr must be sys.stderr — never PIPE (swallows errors) "
        "or STDOUT (merges with proto wire)"
    )


def test_run_op_build_never_uses_capture_output(workspace: Path) -> None:
    """capture_output=True must never be used — it silences all build output."""
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    kwargs = mock_run.call_args.kwargs
    assert not kwargs.get("capture_output", False), (
        "capture_output must never be True — agents would see no build output"
    )


def test_run_op_build_never_pipes_stdout(workspace: Path) -> None:
    """stdout=subprocess.PIPE must never be used on a 30-min build."""
    with _with_docker(), _mock_run(workspace) as mock_run:
        run_op_build(str(workspace), "ghcr.io/org")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("stdout") is not subprocess.PIPE, (
        "stdout=PIPE without draining deadlocks on large builds"
    )
