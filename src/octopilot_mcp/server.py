"""
server.py — Octopilot MCP server (FastMCP 3.x).

Exposes Octopilot's CI/CD capabilities as callable MCP tools so AI agents
(Claude, Cursor, GitHub Copilot, etc.) can detect, generate, build, and
wire up new repositories end-to-end.

Most tools (detect, generate, onboard, actions registry) need NO external
dependencies — pure Python, works out of the box.

run_op_build needs op.  Two options:

  Option A — Container mode (recommended for agents, zero binary install)
  ──────────────────────────────────────────────────────────────────────
  Set OP_USE_CONTAINER=true.  Docker must be running.
  The op container (ghcr.io/octopilot/op:latest) is pulled automatically.

    {
      "mcpServers": {
        "octopilot": {
          "command": "uv",
          "args": ["run", "--directory", "/path/to/octopilot-mcp", "octopilot-mcp"],
          "env": { "OP_USE_CONTAINER": "true" }
        }
      }
    }

  Option B — Local binary
  ──────────────────────────────────────────────────────────────────────
  Download op from https://github.com/octopilot/octopilot-pipeline-tools/releases
  and point to it with OP_BINARY.

    {
      "mcpServers": {
        "octopilot": {
          "command": "uv",
          "args": ["run", "--directory", "/path/to/octopilot-mcp", "octopilot-mcp"],
          "env": { "OP_BINARY": "/usr/local/bin/op" }
        }
      }
    }

Quick start (FastMCP 3 CLI)
───────────────────────────
# Development with hot-reload
    uv run fastmcp dev src/octopilot_mcp/server.py --reload

# Register with Cursor (container mode — no binary needed)
    uv run fastmcp install cursor src/octopilot_mcp/server.py \
        --name octopilot \
        --env OP_USE_CONTAINER=true

# Register with Claude Desktop
    uv run fastmcp install claude src/octopilot_mcp/server.py \
        --name octopilot \
        --env OP_USE_CONTAINER=true

# List tools
    uv run fastmcp list src/octopilot_mcp/server.py
"""

from __future__ import annotations

import json
import textwrap

from fastmcp import FastMCP

from .tools.actions import get_action_details, list_actions
from .tools.detect import detect_project_contexts
from .tools.generate import generate_ci_workflow, generate_skaffold_yaml, onboard_repository
from .tools.op_runner import run_op_build

mcp = FastMCP(
    name="octopilot",
    instructions=textwrap.dedent("""\
        Octopilot provides a "path to production" for applications built with
        Cloud Native Buildpacks and Skaffold. This MCP server lets you:

        1. Detect languages and versions from skaffold.yaml (detect_project_contexts)
        2. Generate skaffold.yaml and .github/workflows/ci.yml (generate_* tools)
        3. Run op build locally or via container (run_op_build)
        4. Discover all available GitHub Actions (list_actions, get_action_details)
        5. Onboard a new repo in one call (onboard_repository)

        Typical onboarding flow:
            onboard_repository(workspace, registry) → returns files to create + next steps

        NOTE: Image promotion (op promote-image) is NOT available here.
        Promotion between environments is operationally sensitive and must only
        run through a GitHub Actions workflow with audit trail and environment
        protection rules. Use generate_ci_workflow to produce that workflow.
    """),
)

# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
def tool_detect_project_contexts(workspace: str) -> dict:
    """
    Parse skaffold.yaml in the workspace and return a pipeline-context JSON object.

    The pipeline-context is consumed by lint, test, janitor, and ci workflow
    generation. It contains the detected languages, versions, and build matrix.

    Args:
        workspace: Absolute path to the repository root (must contain skaffold.yaml).
    """
    return detect_project_contexts(workspace)


@mcp.tool()
def tool_generate_skaffold_yaml(
    artifacts: list[dict],
    builder: str = "ghcr.io/octopilot/builder-jammy-base:latest",
) -> str:
    """
    Generate a skaffold.yaml for the given build artifacts.

    Args:
        artifacts: List of {"name": str, "context": str} dicts.
                   'name' is the image name; 'context' is the relative path to the source.
        builder: Cloud Native Buildpack builder image to use.

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
    Generate a complete .github/workflows/ci.yml for the repository.

    Implements the standard octopilot pipeline pattern:
        detect → lint + test (parallel) → build-container → publish-release (tags only)

    Includes: detect-contexts, lint (with golangci-lint for Go), test (matrix),
    janitor disk cleanup, QEMU, GHCR login, octopilot build action, and SLSA attestation.

    Args:
        pipeline_context: Output from detect_project_contexts().
        registry: Target container registry and org, e.g. "ghcr.io/my-org".
        platforms: Comma-separated platform list (default: linux/amd64,linux/arm64).
        golangci_lint_timeout: Timeout for golangci-lint; increase for large vendor trees.
    """
    return generate_ci_workflow(pipeline_context, registry, platforms, golangci_lint_timeout)


@mcp.tool(timeout=60)
def tool_onboard_repository(
    workspace: str,
    registry: str,
    platforms: str = "linux/amd64,linux/arm64",
    builder: str = "ghcr.io/octopilot/builder-jammy-base:latest",
) -> dict:
    """
    Onboard a repository end-to-end in a single call.

    Detects the project languages, generates skaffold.yaml (if missing) and
    .github/workflows/ci.yml, and returns a ready-to-commit file set plus a
    checklist of remaining manual steps.

    Args:
        workspace: Absolute path to the repository root.
        registry: Container registry and org, e.g. "ghcr.io/my-org".
        platforms: Target build platforms.
        builder: Buildpack builder image.

    Returns:
        {
            "pipeline_context": {...},
            "skaffold_yaml": "...",   // null if skaffold.yaml already existed
            "ci_workflow": "...",
            "files_to_create": ["skaffold.yaml", ".github/workflows/ci.yml"],
            "next_steps": ["..."]
        }
    """
    return onboard_repository(workspace, registry, platforms, builder)


@mcp.tool(timeout=1800)  # 30 min — multi-arch buildpack builds are slow
def tool_run_op_build(
    workspace: str,
    registry: str,
    platforms: str = "linux/amd64",
    push: bool = False,
    use_container: bool | None = None,
) -> dict:
    """
    Run `op build` in the workspace.

    Requires op — either via container (recommended) or a local binary.
    Container mode is selected automatically when OP_USE_CONTAINER=true is set
    in the MCP server environment. No local binary is needed in that case.

    Args:
        workspace:     Absolute path to the repository root (must contain skaffold.yaml).
        registry:      Target registry/org, e.g. "ghcr.io/my-org".
        platforms:     Comma-separated platform list.
        push:          If True, push images to the registry after building.
        use_container: Override container mode for this call.
                       None (default) reads OP_USE_CONTAINER from the server env.
                       True forces container mode (Docker required, no binary needed).
                       False forces local binary mode (OP_BINARY or 'op' on PATH).

    Returns:
        Parsed build_result.json as a dict on success.
    """
    return run_op_build(workspace, registry, platforms, push, use_container)


@mcp.tool()
def tool_list_actions() -> list[dict]:
    """
    Return all Octopilot GitHub Actions from the bundled registry.

    Each entry includes: id, title, path, description, features, inputs, outputs.
    Use get_action_details for examples and gotchas.
    """
    return list_actions()


@mcp.tool()
def tool_get_action_details(action_id: str) -> dict | None:
    """
    Return the full spec for a single Octopilot GitHub Action.

    Includes: description, all inputs/outputs, example workflow YAML, and
    known gotchas with symptoms and fixes.

    Args:
        action_id: Action identifier, e.g. "octopilot", "lint", "test", "janitor",
                   "detect-contexts", "release", "sops-decrypt", "setup-tools",
                   "rotate-secret", "kubernetes-auth", "gke-allow-runner",
                   "eks-allow-runner", "aks-allow-runner".
    """
    return get_action_details(action_id)


# ── Resources ─────────────────────────────────────────────────────────────────


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
                        "name": {"type": "string", "description": "Skaffold artifact image name"},
                        "context": {
                            "type": "string",
                            "description": "Build context path relative to repo root",
                        },
                        "language": {
                            "type": "string",
                            "enum": ["go", "rust", "node", "python", "java"],
                        },
                        "version": {"type": "string", "description": "Detected language version"},
                        "command": {
                            "type": "string",
                            "description": "Optional override test command",
                        },
                    },
                    "required": ["name", "context", "language"],
                },
            },
            "languages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sorted list of unique detected languages",
            },
            "versions": {
                "type": "object",
                "description": "Map of language → highest detected version",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["matrix", "languages", "versions"],
    }
    return json.dumps(schema, indent=2)


@mcp.resource("octopilot://docs/getting-started")
def resource_getting_started() -> str:
    """Plain-text getting started guide for wiring a new repo to Octopilot."""
    return textwrap.dedent("""\
        # Getting Started with Octopilot

        ## Prerequisites
        - A GitHub repository with source code
        - A container registry (e.g. ghcr.io, ECR, GAR)
        - Docker with QEMU (for multi-arch builds)

        ## Step 1: Add skaffold.yaml
        Define your build artifacts. Each artifact maps an image name to a
        source context directory and a Cloud Native Buildpack builder:

            apiVersion: skaffold/v4beta1
            kind: Config
            build:
              artifacts:
                - image: my-app
                  context: .
                  buildpacks:
                    builder: ghcr.io/octopilot/builder-jammy-base:latest

        Use `onboard_repository(workspace, registry)` to auto-generate this.

        ## Step 2: Add CI workflow
        Use `generate_ci_workflow(pipeline_context, registry)` to produce a
        .github/workflows/ci.yml that implements:
            detect → lint + test → build-container → publish-release (tags only)

        ## Step 3: Configure registry access
        Add these GitHub Actions secrets / permissions:
        - GITHUB_TOKEN with packages:write and attestations:write
        - Docker login step pointing at your registry

        ## Step 4: Add .pre-commit-config.yaml (optional)
        The lint job runs pre-commit. At minimum:
            repos:
              - repo: https://github.com/pre-commit/pre-commit-hooks
                rev: v4.5.0
                hooks:
                  - id: trailing-whitespace
                  - id: end-of-file-fixer
                  - id: check-yaml

        For Go projects, also add:
            - repo: https://github.com/golangci/golangci-lint
              rev: v1.64.8
              hooks:
                - id: golangci-lint
        And a .golangci.yml with run.timeout: 10m

        ## Step 5: Push and tag
        Push your changes. On every push to main, the CI pipeline builds and
        pushes images. On tags (v*), it also attests provenance and can publish
        a GitHub release.
    """)


@mcp.resource("octopilot://docs/skaffold-patterns")
def resource_skaffold_patterns() -> str:
    """Common skaffold.yaml patterns for Octopilot projects."""
    return textwrap.dedent("""\
        # Common skaffold.yaml Patterns

        ## Single service (buildpacks, no Dockerfile)
        apiVersion: skaffold/v4beta1
        kind: Config
        build:
          artifacts:
            - image: my-api
              context: .
              buildpacks:
                builder: ghcr.io/octopilot/builder-jammy-base:latest

        ## Two services (frontend + API)
        build:
          artifacts:
            - image: my-app-frontend
              context: frontend
              buildpacks:
                builder: ghcr.io/octopilot/builder-jammy-base:latest
            - image: my-app-api
              context: api
              buildpacks:
                builder: ghcr.io/octopilot/builder-jammy-base:latest

        ## Custom base image + application (two-artifact pattern)
        ## Use when you need a custom runtime environment.
        build:
          artifacts:
            - image: my-app-base
              context: base
              docker:
                dockerfile: Dockerfile
            - image: my-app
              context: .
              buildpacks:
                builder: ghcr.io/octopilot/builder-jammy-base:latest
                runImage: my-app-base

        ## Go project with specific version
        build:
          artifacts:
            - image: my-go-service
              context: .
              buildpacks:
                builder: ghcr.io/octopilot/builder-jammy-base:latest
                env:
                  - GOFLAGS=-buildvcs=false
                  - BP_GO_BUILD_FLAGS=-buildvcs=false
                  # BP_GO_VERSION set by the pipeline from go.mod
    """)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
