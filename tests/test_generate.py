"""Tests for CI workflow and skaffold.yaml generation."""

import yaml

from octopilot_mcp.tools.generate import generate_ci_workflow, generate_skaffold_yaml


def test_generate_skaffold_yaml_single() -> None:
    result = generate_skaffold_yaml([{"name": "my-api", "context": "."}])
    doc = yaml.safe_load(result)
    assert doc["apiVersion"] == "skaffold/v4beta1"
    artifacts = doc["build"]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["image"] == "my-api"
    assert "buildpacks" in artifacts[0]


def test_generate_skaffold_yaml_multi() -> None:
    result = generate_skaffold_yaml(
        [
            {"name": "frontend", "context": "frontend"},
            {"name": "api", "context": "api"},
        ]
    )
    doc = yaml.safe_load(result)
    assert len(doc["build"]["artifacts"]) == 2


def test_generate_ci_workflow_contains_key_sections() -> None:
    pipeline_context = {
        "matrix": [{"name": "api", "context": ".", "language": "go", "version": "1.25.6"}],
        "languages": ["go"],
        "versions": {"go": "1.25.6"},
    }
    result = generate_ci_workflow(pipeline_context, "ghcr.io/my-org")

    assert "detect:" in result
    assert "lint:" in result
    assert "test:" in result
    assert "build-container:" in result
    assert "octopilot/actions/lint@main" in result
    assert "octopilot/actions/octopilot@main" in result
    assert "octopilot/actions/janitor@main" in result
    assert "golangci-lint-timeout" in result  # Go-specific input present


def test_generate_ci_workflow_no_go_timeout() -> None:
    pipeline_context = {
        "matrix": [{"name": "api", "context": ".", "language": "rust", "version": "stable"}],
        "languages": ["rust"],
        "versions": {"rust": "stable"},
    }
    result = generate_ci_workflow(pipeline_context, "ghcr.io/my-org")
    # golangci-lint-timeout should NOT appear for non-Go projects
    assert "golangci-lint-timeout" not in result


def test_generate_ci_workflow_parses_as_yaml() -> None:
    pipeline_context = {
        "matrix": [],
        "languages": [],
        "versions": {},
    }
    result = generate_ci_workflow(pipeline_context, "ghcr.io/my-org")
    # Should be valid YAML
    doc = yaml.safe_load(result)
    assert "jobs" in doc
    assert "detect" in doc["jobs"]
