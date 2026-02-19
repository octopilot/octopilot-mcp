"""Extended tests for language detection — version extraction edge cases."""

from __future__ import annotations

import textwrap
from pathlib import Path

from octopilot_mcp.tools.detect import (
    _detect_go,
    _detect_java,
    _detect_node,
    _detect_python,
    _detect_rust,
    detect_project_contexts,
)


def w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


# ── _detect_go ────────────────────────────────────────────────────────────────


def test_detect_go_version(tmp_path: Path) -> None:
    w(tmp_path / "go.mod", "module example.com/app\n\ngo 1.25.6\n")
    assert _detect_go(tmp_path) == "1.25.6"


def test_detect_go_no_go_mod(tmp_path: Path) -> None:
    assert _detect_go(tmp_path) == ""


def test_detect_go_go_mod_without_version(tmp_path: Path) -> None:
    w(tmp_path / "go.mod", "module example.com/app\n")
    assert _detect_go(tmp_path) == ""


# ── _detect_rust ──────────────────────────────────────────────────────────────


def test_detect_rust_toolchain_toml(tmp_path: Path) -> None:
    w(tmp_path / "rust-toolchain.toml", "[toolchain]\nchannel = 'stable'\n")
    assert _detect_rust(tmp_path) == "stable"


def test_detect_rust_toolchain_plain_file(tmp_path: Path) -> None:
    w(tmp_path / "rust-toolchain", "nightly")
    assert _detect_rust(tmp_path) == "nightly"


def test_detect_rust_no_toolchain(tmp_path: Path) -> None:
    assert _detect_rust(tmp_path) == ""


def test_detect_rust_toml_missing_channel(tmp_path: Path) -> None:
    w(tmp_path / "rust-toolchain.toml", "[toolchain]\n")
    assert _detect_rust(tmp_path) == ""


def test_detect_rust_toml_parse_error(tmp_path: Path) -> None:
    """Invalid TOML is treated as a plain text toolchain file (stripped)."""
    w(tmp_path / "rust-toolchain.toml", "stable\n")
    # .toml parse fails → falls back to returning stripped content
    assert _detect_rust(tmp_path) == "stable"


# ── _detect_node ──────────────────────────────────────────────────────────────


def test_detect_node_package_json_engines(tmp_path: Path) -> None:
    w(tmp_path / "package.json", '{"engines": {"node": "20"}}')
    assert _detect_node(tmp_path) == "20"


def test_detect_node_nvmrc(tmp_path: Path) -> None:
    w(tmp_path / ".nvmrc", "18.12.0\n")
    assert _detect_node(tmp_path) == "18.12.0"


def test_detect_node_package_json_no_engines(tmp_path: Path) -> None:
    w(tmp_path / "package.json", '{"name": "my-app"}')
    assert _detect_node(tmp_path) == ""


def test_detect_node_invalid_json(tmp_path: Path) -> None:
    w(tmp_path / "package.json", "not json")
    assert _detect_node(tmp_path) == ""


def test_detect_node_none(tmp_path: Path) -> None:
    assert _detect_node(tmp_path) == ""


# ── _detect_python ────────────────────────────────────────────────────────────


def test_detect_python_pyproject_toml(tmp_path: Path) -> None:
    w(tmp_path / "pyproject.toml", "[project]\nrequires-python = '>=3.11'\n")
    assert _detect_python(tmp_path) == ">=3.11"


def test_detect_python_version_file(tmp_path: Path) -> None:
    w(tmp_path / ".python-version", "3.12.3\n")
    assert _detect_python(tmp_path) == "3.12.3"


def test_detect_python_none(tmp_path: Path) -> None:
    assert _detect_python(tmp_path) == ""


def test_detect_python_pyproject_parse_error(tmp_path: Path) -> None:
    """Invalid TOML in pyproject.toml falls back to empty string."""
    w(tmp_path / "pyproject.toml", "not valid toml = = =")
    assert _detect_python(tmp_path) == ""


# ── _detect_java ──────────────────────────────────────────────────────────────


def test_detect_java_pom_xml_java_version(tmp_path: Path) -> None:
    w(tmp_path / "pom.xml", "<project><java.version>17</java.version></project>")
    assert _detect_java(tmp_path) == "17"


def test_detect_java_pom_xml_compiler_source(tmp_path: Path) -> None:
    w(tmp_path / "pom.xml", "<project><maven.compiler.source>11</maven.compiler.source></project>")
    assert _detect_java(tmp_path) == "11"


def test_detect_java_build_gradle(tmp_path: Path) -> None:
    w(tmp_path / "build.gradle", "sourceCompatibility = '17'\n")
    assert _detect_java(tmp_path) == "17"


def test_detect_java_none(tmp_path: Path) -> None:
    assert _detect_java(tmp_path) == ""


# ── detect_project_contexts — multiple language versions ─────────────────────


def _make_skaffold(root: Path, *pairs):
    import yaml

    config = {
        "apiVersion": "skaffold/v4beta1",
        "kind": "Config",
        "build": {"artifacts": [{"image": img, "context": ctx} for img, ctx in pairs]},
    }
    (root / "skaffold.yaml").write_text(yaml.dump(config))


def test_detect_picks_highest_version(tmp_path: Path) -> None:
    """When two go artifacts exist, the highest version wins."""
    _make_skaffold(tmp_path, ("svc-a", "svc-a"), ("svc-b", "svc-b"))
    w(tmp_path / "svc-a" / "go.mod", "module a\n\ngo 1.22\n")
    w(tmp_path / "svc-b" / "go.mod", "module b\n\ngo 1.24\n")
    ctx = detect_project_contexts(tmp_path)
    assert ctx["versions"]["go"] == "1.24"


def test_detect_java(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("api", "api"))
    w(tmp_path / "api" / "pom.xml", "<project><java.version>17</java.version></project>")
    ctx = detect_project_contexts(tmp_path)
    assert ctx["languages"] == ["java"]
    assert ctx["versions"]["java"] == "17"


def test_detect_python(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("app", "app"))
    w(tmp_path / "app" / "requirements.txt", "fastapi>=0.100\n")
    ctx = detect_project_contexts(tmp_path)
    assert ctx["languages"] == ["python"]


def test_detect_node(tmp_path: Path) -> None:
    _make_skaffold(tmp_path, ("ui", "ui"))
    w(tmp_path / "ui" / "package.json", '{"name":"ui","engines":{"node":"20"}}')
    ctx = detect_project_contexts(tmp_path)
    assert ctx["languages"] == ["node"]
    assert ctx["versions"]["node"] == "20"
