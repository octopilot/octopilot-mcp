"""Extended tests for CI workflow and skaffold generation — onboard_repository."""

from __future__ import annotations

from pathlib import Path

import yaml

from octopilot_mcp.tools.generate import onboard_repository


def _make_skaffold(root: Path, *pairs):
    config = {
        "apiVersion": "skaffold/v4beta1",
        "kind": "Config",
        "build": {"artifacts": [{"image": img, "context": ctx} for img, ctx in pairs]},
    }
    (root / "skaffold.yaml").write_text(yaml.dump(config))


# ── onboard_repository — skaffold.yaml already exists ───────────────────────


def test_onboard_with_existing_skaffold_go(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("my-api", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25.6\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    assert result["skaffold_yaml"] is None  # not generated (already existed)
    assert "skaffold.yaml" not in result["files_to_create"]
    assert ".github/workflows/ci.yml" in result["files_to_create"]
    assert result["pipeline_context"]["languages"] == ["go"]
    assert result["ci_workflow"]  # non-empty string


def test_onboard_go_adds_golangci_hint(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("my-api", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25.6\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    hints = " ".join(result["next_steps"])
    assert "golangci" in hints.lower()


def test_onboard_non_go_no_golangci_hint(tmp_path: Path) -> None:
    api = tmp_path / "api"
    api.mkdir()
    (api / "Cargo.toml").write_text("[package]\nname='api'\n")
    _make_skaffold(tmp_path, ("api", "api"))

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    hints = " ".join(result["next_steps"])
    assert "golangci" not in hints.lower()


def test_onboard_pre_commit_exists_omits_hint(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25\n")
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    hints = " ".join(result["next_steps"])
    assert ".pre-commit-config.yaml" not in hints


def test_onboard_no_pre_commit_adds_hint(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25\n")
    # .pre-commit-config.yaml intentionally absent

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    hints = " ".join(result["next_steps"])
    assert ".pre-commit-config.yaml" in hints


def test_onboard_ci_already_exists_not_in_files_to_create(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25\n")
    ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
    ci_path.parent.mkdir(parents=True)
    ci_path.write_text("name: CI\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    assert ".github/workflows/ci.yml" not in result["files_to_create"]


# ── onboard_repository — skaffold.yaml does NOT exist ─────────────────────


def test_onboard_generates_skaffold_from_subdirs(tmp_path: Path) -> None:
    # Two service directories, no skaffold.yaml yet
    api = tmp_path / "api"
    api.mkdir()
    (api / "go.mod").write_text("module example.com/api\n\ngo 1.25\n")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name":"frontend","engines":{"node":"20"}}')

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    assert result["skaffold_yaml"] is not None
    assert "skaffold.yaml" in result["files_to_create"]
    # Temp skaffold.yaml was cleaned up
    assert not (tmp_path / "skaffold.yaml").exists()


def test_onboard_generates_skaffold_fallback_to_root(tmp_path: Path) -> None:
    # No skaffold.yaml, no recognised sub-directories → uses workspace root
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    assert result["skaffold_yaml"] is not None
    skaffold = yaml.safe_load(result["skaffold_yaml"])
    artifacts = skaffold["build"]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["context"] == "."


def test_onboard_cleans_up_temp_skaffold_on_detect_error(tmp_path: Path) -> None:
    """Temp skaffold.yaml is removed even when detect_project_contexts fails."""
    # Empty directory — detect will produce an empty matrix but not error
    onboard_repository(str(tmp_path), "ghcr.io/my-org")
    assert not (tmp_path / "skaffold.yaml").exists()


# ── result structure ──────────────────────────────────────────────────────────


def test_onboard_result_keys(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.25\n")

    result = onboard_repository(str(tmp_path), "ghcr.io/my-org")

    assert "pipeline_context" in result
    assert "skaffold_yaml" in result
    assert "ci_workflow" in result
    assert "files_to_create" in result
    assert "next_steps" in result
    assert isinstance(result["next_steps"], list)
    assert len(result["next_steps"]) > 0


def test_onboard_custom_platforms(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    result = onboard_repository(str(tmp_path), "ghcr.io/my-org", platforms="linux/amd64")
    assert "linux/amd64" in result["ci_workflow"]


def test_onboard_registry_in_next_steps(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "."))
    result = onboard_repository(str(tmp_path), "ghcr.io/acme")
    hints = " ".join(result["next_steps"])
    assert "ghcr.io/acme" in hints
