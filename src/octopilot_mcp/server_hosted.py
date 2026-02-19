"""
server_hosted.py — Hosted MCP server for https://mcp.octopilot.app

Exposes only the stateless, read-only tools that are safe to run on a shared
public server. Tools that need local filesystem access or Docker (detect,
onboard, run_op_build) are intentionally absent — those require the locally
installed version.

Hosted tools (no local dependencies):
  list_actions            Browse the Octopilot GitHub Actions registry
  get_action_details      Full spec, inputs, examples, gotchas for one action
  generate_skaffold_yaml  Generate a skaffold.yaml for given artifacts
  generate_ci_workflow    Full .github/workflows/ci.yml for a project

Install directly (no clone needed):
  fastmcp install cursor  https://mcp.octopilot.app
  fastmcp install claude  https://mcp.octopilot.app
"""

from __future__ import annotations

import os
import textwrap

from fastmcp import FastMCP

from .tools.actions import get_action_details, list_actions
from .tools.generate import generate_ci_workflow, generate_skaffold_yaml

mcp = FastMCP(
    name="octopilot",
    instructions=textwrap.dedent("""\
        Octopilot provides a "path to production" for applications built with
        Cloud Native Buildpacks and Skaffold. This hosted server exposes the
        stateless tools — no local installation or Docker required.

        Available tools:
          list_actions              Browse all Octopilot GitHub Actions
          get_action_details        Full spec for one action (inputs, examples, gotchas)
          generate_skaffold_yaml    Generate a skaffold.yaml for given artifacts
          generate_ci_workflow      Full .github/workflows/ci.yml for a project

        For the full tool suite (including detect_project_contexts, run_op_build,
        and onboard_repository) install the server locally:
          pip install octopilot-mcp
          fastmcp install cursor src/octopilot_mcp/server.py --name octopilot
    """),
)

# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
def tool_list_actions() -> list[dict]:
    """
    Return all Octopilot GitHub Actions from the registry.

    Each entry includes: id, title, path, description, features, inputs, outputs.
    """
    return list_actions()


@mcp.tool()
def tool_get_action_details(action_id: str) -> dict | None:
    """
    Return the full spec for a single Octopilot GitHub Action.

    Includes: description, all inputs/outputs, example workflow YAML, and
    known gotchas with symptoms and fixes.

    Args:
        action_id: e.g. "octopilot", "lint", "test", "janitor", "release",
                   "detect-contexts", "sops-decrypt", "setup-tools",
                   "rotate-secret", "kubernetes-auth", "gke-allow-runner",
                   "eks-allow-runner", "aks-allow-runner".
    """
    return get_action_details(action_id)


@mcp.tool()
def tool_generate_skaffold_yaml(
    artifacts: list[dict],
    builder: str = "ghcr.io/octopilot/builder-jammy-base:latest",
) -> str:
    """
    Generate a skaffold.yaml for the given build artifacts.

    Args:
        artifacts: List of {"name": str, "context": str} dicts.
        builder:   Cloud Native Buildpack builder image.

    Returns:
        YAML string ready to write to skaffold.yaml.
    """
    return generate_skaffold_yaml(artifacts, builder)


@mcp.tool()
def tool_generate_ci_workflow(
    pipeline_context: dict,
    registry: str,
    platforms: str = "linux/amd64,linux/arm64",
    golangci_lint_timeout: str = "10m",
) -> str:
    """
    Generate a complete .github/workflows/ci.yml for a repository.

    Implements the standard octopilot pipeline:
        detect → lint + test (parallel) → build-container → publish-release

    Args:
        pipeline_context:      Output from detect_project_contexts (or hand-crafted).
                               {"matrix": [...], "languages": [...], "versions": {...}}
        registry:              Target container registry, e.g. "ghcr.io/my-org".
        platforms:             Comma-separated platform list.
        golangci_lint_timeout: Timeout for golangci-lint (Go projects).
    """
    return generate_ci_workflow(pipeline_context, registry, platforms, golangci_lint_timeout)


# ── Resources ─────────────────────────────────────────────────────────────────

import json  # noqa: E402  (import after tools to keep tool defs at top)


@mcp.resource("octopilot://actions")
def resource_actions() -> str:
    """Full Octopilot actions registry as JSON."""
    return json.dumps(list_actions(), indent=2)


@mcp.resource("octopilot://pipeline-context-schema")
def resource_pipeline_context_schema() -> str:
    """JSON Schema describing the pipeline-context object."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "PipelineContext",
        "type": "object",
        "properties": {
            "matrix": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "context": {"type": "string"},
                        "language": {
                            "type": "string",
                            "enum": ["go", "rust", "node", "python", "java"],
                        },
                        "version": {"type": "string"},
                        "command": {"type": "string"},
                    },
                    "required": ["name", "context", "language"],
                },
            },
            "languages": {"type": "array", "items": {"type": "string"}},
            "versions": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "required": ["matrix", "languages", "versions"],
    }
    return json.dumps(schema, indent=2)


# ── Install script endpoint ───────────────────────────────────────────────────
# Serves the install script at GET /install so that:
#   curl -fsSL https://mcp.octopilot.app/install | sh
# works without needing the website or GitHub raw URLs.

import importlib.resources  # noqa: E402


def _load_install_script() -> str:
    """Load install.sh bundled with the package, or fall back to a redirect notice."""
    try:
        # When installed as a package, install.sh is bundled in the data dir
        data_path = importlib.resources.files("octopilot_mcp") / "data" / "install.sh"
        return data_path.read_text(encoding="utf-8")
    except Exception:
        # Fallback: redirect to GitHub
        return (
            "#!/usr/bin/env sh\n"
            "# Redirect to canonical install script\n"
            'exec curl -fsSL "https://raw.githubusercontent.com/octopilot/octopilot-mcp/main/install.sh" | sh\n'
        )


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse, RedirectResponse
    from starlette.routing import Mount, Route

    port = int(os.environ.get("PORT", "8000"))
    install_script = _load_install_script()

    async def handle_install(request: Request) -> PlainTextResponse:
        """Return the install.sh script with the correct content-type for pipe-to-sh."""
        return PlainTextResponse(install_script, media_type="text/plain")

    async def handle_root(request: Request) -> RedirectResponse:
        """Redirect bare / to the docs page."""
        return RedirectResponse(url="https://octopilot.app/docs/mcp", status_code=302)

    # FastMCP 3 exposes the underlying ASGI app so we can wrap it with
    # custom Starlette routes before handing off to uvicorn.
    mcp_asgi = mcp.http_app(transport="streamable-http")

    app = Starlette(
        routes=[
            Route("/install", handle_install, methods=["GET"]),
            Route("/", handle_root, methods=["GET"]),
            Mount("/", app=mcp_asgi),
        ]
    )

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
