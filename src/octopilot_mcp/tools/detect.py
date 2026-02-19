"""
detect.py — Language and version detection from skaffold.yaml.

Ports the logic from octopilot/actions/detect-contexts/detect.py so the MCP
server can analyse a workspace without requiring the action to be installed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

import yaml


def _read(context: Path, filename: str) -> str | None:
    try:
        return (context / filename).read_text()
    except OSError:
        return None


def _detect_go(context: Path) -> str:
    content = _read(context, "go.mod")
    if content:
        m = re.search(r"^go\s+(\S+)", content, re.MULTILINE)
        if m:
            return m.group(1)
    return ""


def _detect_rust(context: Path) -> str:
    for f in ["rust-toolchain.toml", "rust-toolchain"]:
        content = _read(context, f)
        if content:
            if f.endswith(".toml"):
                try:
                    return tomllib.loads(content).get("toolchain", {}).get("channel", "")
                except Exception:
                    pass
            return content.strip()
    return ""


def _detect_node(context: Path) -> str:
    content = _read(context, "package.json")
    if content:
        try:
            v = json.loads(content).get("engines", {}).get("node", "")
            if v:
                return v
        except json.JSONDecodeError:
            pass
    content = _read(context, ".nvmrc")
    if content:
        return content.strip()
    return ""


def _detect_python(context: Path) -> str:
    content = _read(context, "pyproject.toml")
    if content:
        try:
            v = tomllib.loads(content).get("project", {}).get("requires-python", "")
            if v:
                return v
        except Exception:
            pass
    content = _read(context, ".python-version")
    if content:
        return content.strip()
    return ""


def _detect_java(context: Path) -> str:
    content = _read(context, "pom.xml")
    if content:
        m = re.search(r"<java\.version>(.*?)</java\.version>", content)
        if m:
            return m.group(1)
        m = re.search(r"<maven\.compiler\.source>(.*?)</maven\.compiler\.source>", content)
        if m:
            return m.group(1)
    content = _read(context, "build.gradle")
    if content:
        m = re.search(r"sourceCompatibility\s*=\s*['\"]?(.*?)['\"]", content)
        if m:
            return m.group(1)
    return ""


def _detect_project_info(context_path: Path) -> dict | None:
    if not context_path.exists():
        return None
    try:
        files = {f.name for f in context_path.iterdir()}
    except OSError:
        return None

    if "go.mod" in files:
        return {"language": "go", "version": _detect_go(context_path)}
    if "Cargo.toml" in files:
        return {"language": "rust", "version": _detect_rust(context_path)}
    if "package.json" in files:
        return {"language": "node", "version": _detect_node(context_path)}
    if files & {"requirements.txt", "pyproject.toml", "Pipfile"}:
        return {"language": "python", "version": _detect_python(context_path)}
    if files & {"pom.xml", "build.gradle", "build.gradle.kts"}:
        return {"language": "java", "version": _detect_java(context_path)}
    return None


def detect_project_contexts(workspace: str | Path) -> dict:
    """
    Parse skaffold.yaml in *workspace* and return a pipeline-context object
    identical to what octopilot/actions/detect-contexts produces.

    Returns:
        {
            "matrix": [{"name": str, "context": str, "language": str, "version": str}],
            "languages": [str, ...],
            "versions": {"go": "1.25.6", ...}
        }

    Raises FileNotFoundError if skaffold.yaml is not found.
    """
    workspace = Path(workspace)
    skaffold_file = workspace / "skaffold.yaml"
    if not skaffold_file.exists():
        raise FileNotFoundError(f"skaffold.yaml not found in {workspace}")

    with skaffold_file.open() as f:
        config = yaml.safe_load(f)

    artifacts = config.get("build", {}).get("artifacts", [])
    matrix: list[dict] = []

    for artifact in artifacts:
        image = artifact.get("image", "")
        context_rel = artifact.get("context", ".")
        context_path = workspace / context_rel

        info = _detect_project_info(context_path)
        if info:
            matrix.append({
                "name": image,
                "context": context_rel,
                "language": info["language"],
                "version": info["version"],
            })

    languages = sorted({item["language"] for item in matrix if item.get("language")})
    versions = {}
    for lang in languages:
        lang_versions = {
            item["version"] for item in matrix
            if item.get("language") == lang and item.get("version")
        }
        if lang_versions:
            versions[lang] = sorted(lang_versions)[-1]

    return {"matrix": matrix, "languages": languages, "versions": versions}
