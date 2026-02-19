"""
generate.py — CI workflow and skaffold.yaml generation tools.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

DEFAULT_BUILDER = "ghcr.io/octopilot/builder-jammy-base:latest"


def generate_skaffold_yaml(
    artifacts: list[dict],
    builder: str = DEFAULT_BUILDER,
) -> str:
    """
    Generate a skaffold.yaml for the given artifacts.

    Args:
        artifacts: list of {"name": str, "context": str} dicts.
        builder: Cloud Native Buildpack builder image.

    Returns:
        YAML string ready to write to skaffold.yaml.
    """
    config = {
        "apiVersion": "skaffold/v4beta1",
        "kind": "Config",
        "build": {
            "artifacts": [
                {
                    "image": art["name"],
                    "context": art["context"],
                    "buildpacks": {"builder": builder},
                }
                for art in artifacts
            ]
        },
    }
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def generate_ci_workflow(
    pipeline_context: dict,
    registry: str,
    platforms: str = "linux/amd64,linux/arm64",
    golangci_lint_timeout: str = "10m",
) -> str:
    """
    Generate a complete .github/workflows/ci.yml for a repository.

    Implements the standard octopilot pipeline:
        detect → lint + test (parallel) → build-container → publish-release (tags only)

    Args:
        pipeline_context: Output from detect_project_contexts().
        registry: Target container registry, e.g. "ghcr.io/my-org".
        platforms: Comma-separated platform list.
        golangci_lint_timeout: Timeout for golangci-lint (Go projects).

    Returns:
        YAML string ready to write to .github/workflows/ci.yml.
    """
    has_go = "go" in pipeline_context.get("languages", [])
    lint_with_extras = ""
    if has_go:
        lint_with_extras = f"\n          golangci-lint-timeout: {golangci_lint_timeout!r}"

    return textwrap.dedent(f"""\
        name: CI

        on:
          push:
            branches: [main]
            tags: ["v*"]
          pull_request:
            branches: [main]
          workflow_dispatch:

        jobs:
          detect:
            name: Detect Contexts
            runs-on: ubuntu-latest
            outputs:
              pipeline-context: ${{{{ steps.detect.outputs.pipeline-context }}}}
            steps:
              - uses: actions/checkout@v4
              - id: detect
                uses: octopilot/actions/detect-contexts@main

          lint:
            needs: detect
            if: toJSON(fromJson(needs.detect.outputs.pipeline-context).languages) != '[]'
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: octopilot/actions/lint@main
                with:
                  pipeline-context: ${{{{ needs.detect.outputs.pipeline-context }}}}{lint_with_extras}

          test:
            needs: detect
            if: toJSON(fromJson(needs.detect.outputs.pipeline-context).matrix) != '[]'
            runs-on: ubuntu-latest
            strategy:
              matrix:
                include: ${{{{ fromJson(needs.detect.outputs.pipeline-context).matrix }}}}
            steps:
              - uses: actions/checkout@v4
              - uses: octopilot/actions/test@main
                with:
                  pipeline-context: ${{{{ toJson(matrix) }}}}

          build-container:
            name: Build and Push Container
            needs: [detect, lint, test]
            if: github.event_name == 'push'
            runs-on: ubuntu-latest
            permissions:
              contents: read
              packages: write
              id-token: write
              attestations: write
            outputs:
              digest: ${{{{ steps.op-digest.outputs.digest }}}}
            steps:
              - uses: actions/checkout@v4

              - name: Free runner disk space
                uses: octopilot/actions/janitor@main

              - uses: docker/setup-qemu-action@v3

              - uses: docker/login-action@v3
                with:
                  registry: ghcr.io
                  username: ${{{{ github.actor }}}}
                  password: ${{{{ secrets.GITHUB_TOKEN }}}}

              - name: Build and Push
                id: push
                uses: octopilot/actions/octopilot@main
                with:
                  version: ${{{{ github.ref_name }}}}
                  registry: {registry}
                  platforms: {platforms}

              - name: Extract application image digest
                id: op-digest
                run: |
                  # Select the application image (last entry) — base images appear first.
                  TAG=$(jq -r '.builds[-1].tag' build_result.json)
                  DIGEST=$(echo "$TAG" | awk -F'@' '{{print $2}}')
                  echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
                  echo "Attesting: $TAG"

              - name: Attest Build Provenance
                if: startsWith(github.ref, 'refs/tags/v') && steps.op-digest.outputs.digest != ''
                uses: actions/attest-build-provenance@v2
                with:
                  subject-name: ${{{{ steps.push.outputs.image || '' }}}}
                  subject-digest: ${{{{ steps.op-digest.outputs.digest }}}}
                  push-to-registry: true
    """)


def onboard_repository(
    workspace: str | Path,
    registry: str,
    platforms: str = "linux/amd64,linux/arm64",
    builder: str = DEFAULT_BUILDER,
) -> dict:
    """
    High-level onboarding tool.

    Detects the project, generates missing files, and returns a ready-to-commit
    file set plus a checklist of next steps.

    Args:
        workspace: Path to the repository root.
        registry: Container registry, e.g. "ghcr.io/my-org".
        platforms: Target build platforms.
        builder: Buildpack builder image.

    Returns:
        {
            "pipeline_context": {...},
            "skaffold_yaml": "..." | None,   # None if skaffold.yaml already exists
            "ci_workflow": "...",
            "files_to_create": ["skaffold.yaml", ".github/workflows/ci.yml"],
            "next_steps": ["..."]
        }
    """
    # Import here to avoid circular deps at module level
    from .detect import detect_project_contexts

    workspace = Path(workspace)
    skaffold_path = workspace / "skaffold.yaml"
    ci_path = workspace / ".github" / "workflows" / "ci.yml"

    # If no skaffold.yaml, we need to discover artifacts from directory structure
    generated_skaffold: str | None = None
    if not skaffold_path.exists():
        # Heuristic: treat immediate subdirectories with a language indicator as artifacts
        artifacts = []
        for child in sorted(workspace.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                # Check if it looks like a service directory
                has_lang = any(
                    (child / f).exists()
                    for f in [
                        "go.mod",
                        "Cargo.toml",
                        "package.json",
                        "requirements.txt",
                        "pyproject.toml",
                    ]
                )
                if has_lang:
                    artifacts.append({"name": child.name, "context": child.name})
        if not artifacts:
            artifacts = [{"name": workspace.name, "context": "."}]
        generated_skaffold = generate_skaffold_yaml(artifacts, builder)
        # Write temporarily so detect can read it
        skaffold_path.write_text(generated_skaffold)

    try:
        pipeline_context = detect_project_contexts(workspace)
    finally:
        # Clean up temp file if we created it
        if generated_skaffold and skaffold_path.exists():
            skaffold_path.unlink()

    ci_workflow = generate_ci_workflow(pipeline_context, registry, platforms)

    files_to_create = []
    if generated_skaffold:
        files_to_create.append("skaffold.yaml")
    if not ci_path.exists():
        files_to_create.append(".github/workflows/ci.yml")

    languages = pipeline_context.get("languages", [])
    next_steps = [
        "Ensure GITHUB_TOKEN has 'packages: write' and 'attestations: write' permissions.",
        f"Log in to {registry} from CI (docker/login-action@v3).",
    ]
    if "go" in languages:
        next_steps.append("Add .golangci.yml with 'run: timeout: 10m' for large vendor trees.")
    if not (workspace / ".pre-commit-config.yaml").exists():
        next_steps.append("Add .pre-commit-config.yaml for the lint job to run hooks.")
    next_steps.append("Push changes — the CI pipeline will trigger on the next push to main.")

    return {
        "pipeline_context": pipeline_context,
        "skaffold_yaml": generated_skaffold,
        "ci_workflow": ci_workflow,
        "files_to_create": files_to_create,
        "next_steps": next_steps,
    }
