"""
op_runner.py — Run the `op build` CLI binary or container.

Two operating modes, selected by environment variable:

  OP_USE_CONTAINER=true   Pull ghcr.io/octopilot/op and run op build inside it.
                          Requires Docker but needs NO local op binary.
                          Recommended for agents and CI environments.

  OP_BINARY=/path/to/op   Use a local op binary.
                          Falls back to the op binary on PATH if set.

When neither is set the server still works for all tools EXCEPT run_op_build,
which will raise an informative error explaining the two options.

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

# Default image used in container mode
_DEFAULT_OP_IMAGE = "ghcr.io/octopilot/op:latest"


def _use_container_mode() -> bool:
    """Return True if OP_USE_CONTAINER env var is set to a truthy value."""
    return os.environ.get("OP_USE_CONTAINER", "").lower() in ("true", "1", "yes")


def _find_op_binary() -> str:
    """
    Locate the op binary.

    Resolution order:
      1. OP_BINARY environment variable
      2. op on PATH

    Raises FileNotFoundError with instructions if not found.
    """
    if env := os.environ.get("OP_BINARY"):
        return env
    found = shutil.which("op")
    if found:
        return found
    raise FileNotFoundError(
        "op binary not found.\n"
        "\n"
        "Choose one of:\n"
        "  A) Set OP_USE_CONTAINER=true in the MCP server env to use the op container\n"
        "     (requires Docker, no binary needed):\n"
        '       "env": { "OP_USE_CONTAINER": "true" }\n'
        "\n"
        "  B) Download the op binary from https://github.com/octopilot/octopilot-pipeline-tools/releases\n"
        "     and point to it:\n"
        '       "env": { "OP_BINARY": "/usr/local/bin/op" }\n'
    )


def run_op_build(
    workspace: str | Path,
    registry: str,
    platforms: str = "linux/amd64",
    push: bool = False,
    use_container: bool | None = None,
    op_image: str = _DEFAULT_OP_IMAGE,
    extra_args: list[str] | None = None,
) -> dict:
    """
    Run `op build` in the given workspace.

    Args:
        workspace:     Path to the repository root (must contain skaffold.yaml).
        registry:      Target registry/org, e.g. "ghcr.io/my-org".
        platforms:     Comma-separated platform list.
        push:          If True, passes --push to op build.
        use_container: If True (or OP_USE_CONTAINER=true in env), run op inside
                       ghcr.io/octopilot/op via Docker — no local binary needed.
                       If None (default), reads OP_USE_CONTAINER from the environment.
        op_image:      Container image for container mode.
        extra_args:    Additional flags passed to op build.

    Returns:
        Parsed build_result.json as a dict, or {"status": "ok"} if not produced.

    Raises:
        subprocess.CalledProcessError: on non-zero exit.
        FileNotFoundError: when no binary and container mode is not enabled.
    """
    workspace = Path(workspace).resolve()

    # Resolve container mode: explicit arg overrides env var
    if use_container is None:
        use_container = _use_container_mode()

    cmd_args = ["build", "--repo", registry, "--platform", platforms]
    if push:
        cmd_args.append("--push")
    if extra_args:
        cmd_args.extend(extra_args)

    if use_container:
        docker_cmd = [
            "docker",
            "run",
            "--rm",
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
            op_image,
            "-c",
            f"op {' '.join(cmd_args)}",
        ]
        subprocess.run(docker_cmd, check=True, cwd=workspace)
    else:
        op_binary = _find_op_binary()
        subprocess.run([op_binary, *cmd_args], check=True, cwd=workspace)

    result_path = workspace / "build_result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    return {"status": "ok", "note": "build_result.json not found after build"}
