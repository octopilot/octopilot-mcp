"""
op_runner.py — Run the `op build` CLI binary or container.

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


def _find_op_binary() -> str:
    """Locate the op binary: OP_BINARY env → PATH → error."""
    if env := os.environ.get("OP_BINARY"):
        return env
    found = shutil.which("op")
    if found:
        return found
    raise FileNotFoundError(
        "op binary not found. Set OP_BINARY env var or ensure 'op' is on PATH."
    )


def run_op_build(
    workspace: str | Path,
    registry: str,
    platforms: str = "linux/amd64",
    push: bool = False,
    use_container: bool = False,
    op_image: str = "ghcr.io/octopilot/op:latest",
    extra_args: list[str] | None = None,
) -> dict:
    """
    Run `op build` in the given workspace.

    Args:
        workspace: Path to the repository root (must contain skaffold.yaml).
        registry: Target registry/org, e.g. "ghcr.io/my-org".
        platforms: Comma-separated platform list.
        push: If True, passes --push to op build.
        use_container: If True, runs op inside the ghcr.io/octopilot/op container
                       via Docker (requires Docker to be running).
        op_image: Container image to use in container mode.
        extra_args: Additional flags passed to op build.

    Returns:
        Parsed build_result.json as a dict, or {"status": "ok"} if not produced.

    Raises:
        subprocess.CalledProcessError on non-zero exit.
    """
    workspace = Path(workspace).resolve()
    cmd_args = ["build", "--repo", registry, "--platform", platforms]
    if push:
        cmd_args.append("--push")
    if extra_args:
        cmd_args.extend(extra_args)

    if use_container:
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace",
            "-e", "GITHUB_ACTIONS=true",
            "--entrypoint", "/bin/sh",
            op_image,
            "-c", f"op {' '.join(cmd_args)}",
        ]
        subprocess.run(docker_cmd, check=True, cwd=workspace)
    else:
        op_binary = _find_op_binary()
        subprocess.run([op_binary] + cmd_args, check=True, cwd=workspace)

    result_path = workspace / "build_result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    return {"status": "ok", "note": "build_result.json not found after build"}
