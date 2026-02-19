"""Tests for the actions registry."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from octopilot_mcp.tools import actions as actions_mod
from octopilot_mcp.tools.actions import _load_registry, get_action_details, list_actions


def _clear_cache() -> None:
    """Clear the lru_cache on _load_registry so tests are isolated."""
    _load_registry.cache_clear()


@pytest.fixture(autouse=True)
def clear_registry_cache():
    """Automatically clear the registry cache before and after every test."""
    _clear_cache()
    yield
    _clear_cache()


# ── _load_registry ────────────────────────────────────────────────────────────


def test_load_registry_missing_file(tmp_path: Path) -> None:
    """Returns empty list when actions.json does not exist."""
    with patch.object(actions_mod, "_DATA_DIR", tmp_path):
        result = _load_registry()
    assert result == []


def test_load_registry_bare_list(tmp_path: Path) -> None:
    """Handles a bare JSON array (not wrapped in {"actions": [...]})."""
    data = [{"id": "test", "title": "Test Action"}]
    (tmp_path / "actions.json").write_text(json.dumps(data))
    with patch.object(actions_mod, "_DATA_DIR", tmp_path):
        result = _load_registry()
    assert result == data


def test_load_registry_dict_format(tmp_path: Path) -> None:
    """Handles the {"actions": [...]} wrapper format."""
    data = {"version": "1", "actions": [{"id": "octopilot", "title": "Build"}]}
    (tmp_path / "actions.json").write_text(json.dumps(data))
    with patch.object(actions_mod, "_DATA_DIR", tmp_path):
        result = _load_registry()
    assert len(result) == 1
    assert result[0]["id"] == "octopilot"


def test_load_registry_empty_dict(tmp_path: Path) -> None:
    """Returns empty list when dict has no 'actions' key."""
    (tmp_path / "actions.json").write_text(json.dumps({"version": "1"}))
    with patch.object(actions_mod, "_DATA_DIR", tmp_path):
        result = _load_registry()
    assert result == []


# ── list_actions / get_action_details ─────────────────────────────────────────


def _patch_registry(tmp_path: Path, entries: list[dict]):
    (tmp_path / "actions.json").write_text(json.dumps(entries))
    return patch.object(actions_mod, "_DATA_DIR", tmp_path)


def test_list_actions_returns_all(tmp_path: Path) -> None:
    entries = [
        {"id": "lint", "title": "Lint"},
        {"id": "test", "title": "Test"},
    ]
    with _patch_registry(tmp_path, entries):
        result = list_actions()
    assert len(result) == 2
    assert {a["id"] for a in result} == {"lint", "test"}


def test_list_actions_empty_registry(tmp_path: Path) -> None:
    with _patch_registry(tmp_path, []):
        result = list_actions()
    assert result == []


def test_get_action_details_found(tmp_path: Path) -> None:
    entries = [
        {"id": "octopilot", "title": "Octopilot Build", "inputs": []},
        {"id": "janitor", "title": "Janitor"},
    ]
    with _patch_registry(tmp_path, entries):
        result = get_action_details("octopilot")
    assert result is not None
    assert result["title"] == "Octopilot Build"


def test_get_action_details_not_found(tmp_path: Path) -> None:
    with _patch_registry(tmp_path, [{"id": "lint", "title": "Lint"}]):
        result = get_action_details("nonexistent")
    assert result is None


def test_get_action_details_empty_registry(tmp_path: Path) -> None:
    with _patch_registry(tmp_path, []):
        result = get_action_details("anything")
    assert result is None
