"""
op_runner.py — Run op build via the official container image.

Docker (or Colima) is the only requirement. No local op binary is needed.

The container is always pulled before each run (docker run --pull always)
so agents and developers automatically get the latest op release without
any manual update steps.

Pinning to a specific release (e.g. for reproducible CI):
  Set OP_IMAGE=ghcr.io/octopilot/op:v1.0.0 in the MCP server environment.
  Default is ghcr.io/octopilot/op:latest.

NOTE: op promote-image is intentionally NOT exposed here.
Image promotion between environments is operationally sensitive — it must only
ever run through a GitHub Actions workflow (with audit trail, OIDC credentials,
and environment protection rules). Exposing it to an AI agent via MCP creates
unacceptable risk of accidental or unauthorised promotion to production.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_DEFAULT_OP_IMAGE = "ghcr.io/octopilot/op:latest"


def _get_op_image() -> str:
    """Return the op container image to use. OP_IMAGE env var overrides the default."""
    return os.environ.get("OP_IMAGE", _DEFAULT_OP_IMAGE)


def _assert_docker_available() -> None:
    """Raise RuntimeError with clear instructions if Docker is not on PATH."""
    if not shutil.which("docker"):
        raise RuntimeError(
            "Docker is not available.\n"
            "\n"
            "octopilot-mcp requires Docker (or Colima) to run op commands.\n"
            "\n"
            "  macOS:  brew install --cask docker   (Docker Desktop)\n"
            "          brew install colima && colima start\n"
            "  Linux:  https://docs.docker.com/engine/install/\n"
        )


def run_op_build(
    workspace: str | Path,
    registry: str,
    platforms: str = "linux/amd64",
    push: bool = False,
    op_image: str | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    """
    Run `op build` inside the official op container.

    The image is always pulled before running (--pull always) so the latest
    op release is used automatically. Set OP_IMAGE in the MCP server env to
    pin to a specific version for reproducibility.

    Args:
        workspace:  Path to the repository root (must contain skaffold.yaml).
        registry:   Target registry/org, e.g. "ghcr.io/my-org".
        platforms:  Comma-separated platform list.
        push:       If True, passes --push to op build.
        op_image:   Override the container image for this call.
                    Defaults to OP_IMAGE env var → ghcr.io/octopilot/op:latest.
        extra_args: Additional flags passed to op build.

    Returns:
        Parsed build_result.json as a dict, or {"status": "ok"} if not produced.

    Raises:
        RuntimeError:                   if Docker is not available.
        subprocess.CalledProcessError:  on non-zero exit.
    """
    _assert_docker_available()

    workspace = Path(workspace).resolve()
    image = op_image or _get_op_image()

    cmd_args = ["build", "--repo", registry, "--platform", platforms]
    if push:
        cmd_args.append("--push")
    if extra_args:
        cmd_args.extend(extra_args)

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "always",  # always fetch latest; falls back to cache if offline
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        "-e",
        "GITHUB_ACTIONS=true",
        "--entrypoint",
        "/bin/sh",
        image,
        "-c",
        f"op {' '.join(cmd_args)}",
    ]
    subprocess.run(docker_cmd, check=True, cwd=workspace)

    result_path = workspace / "build_result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    return {"status": "ok", "note": "build_result.json not found after build"}
