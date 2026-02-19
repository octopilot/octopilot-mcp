"""Tests for language detection logic."""
import os
import textwrap
from pathlib import Path

import yaml
import pytest

from octopilot_mcp.tools.detect import detect_project_contexts


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def make_skaffold(root: Path, *contexts: tuple[str, str]) -> None:
    """Write a minimal skaffold.yaml with the given (image, context) pairs."""
    config = {
        "apiVersion": "skaffold/v4beta1",
        "kind": "Config",
        "build": {
            "artifacts": [
                {"image": img, "context": ctx} for img, ctx in contexts
            ]
        },
    }
    (root / "skaffold.yaml").write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False)
    )


def test_detect_go_single(tmp_path: Path) -> None:
    make_skaffold(tmp_path, ("my-service", "."))
    write(tmp_path / "go.mod", "module example.com/app\n\ngo 1.25.6\n")

    ctx = detect_project_contexts(tmp_path)

    assert ctx["languages"] == ["go"]
    assert ctx["versions"]["go"] == "1.25.6"
    assert len(ctx["matrix"]) == 1
    assert ctx["matrix"][0]["language"] == "go"


def test_detect_rust(tmp_path: Path) -> None:
    make_skaffold(tmp_path, ("my-api", "api"))
    api = tmp_path / "api"
    api.mkdir()
    write(api / "Cargo.toml", "[package]\nname = 'my-api'\n")
    write(api / "rust-toolchain.toml", "[toolchain]\nchannel = 'stable'\n")

    ctx = detect_project_contexts(tmp_path)

    assert ctx["languages"] == ["rust"]
    assert ctx["versions"]["rust"] == "stable"


def test_detect_multi_language(tmp_path: Path) -> None:
    make_skaffold(tmp_path, ("frontend", "frontend"), ("api", "api"))
    write(tmp_path / "frontend" / "package.json", '{"engines": {"node": "20"}}')
    write(tmp_path / "api" / "go.mod", "module example.com/api\n\ngo 1.24\n")

    ctx = detect_project_contexts(tmp_path)

    assert set(ctx["languages"]) == {"go", "node"}
    assert len(ctx["matrix"]) == 2


def test_missing_skaffold(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_project_contexts(tmp_path)


def test_unknown_language_skipped(tmp_path: Path) -> None:
    make_skaffold(tmp_path, ("base", "base"))
    (tmp_path / "base").mkdir()
    # No language indicators — artifact should be skipped
    ctx = detect_project_contexts(tmp_path)
    assert ctx["matrix"] == []
    assert ctx["languages"] == []
