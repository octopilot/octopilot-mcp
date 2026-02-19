"""
actions.py — Octopilot actions registry.

Loads the bundled actions.json so agents can discover and understand all
available GitHub Actions without hitting the network.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _load_registry() -> list[dict]:
    path = _DATA_DIR / "actions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    # Support both {"actions": [...]} and a bare list
    if isinstance(data, dict):
        return data.get("actions", [])
    return data


def list_actions() -> list[dict]:
    """
    Return all Octopilot GitHub Actions from the bundled registry.

    Each entry contains: id, title, path, description, features, inputs, outputs.
    """
    return _load_registry()


def get_action_details(action_id: str) -> dict | None:
    """
    Return the full spec for a single action, including example YAML and gotchas.

    Returns None if the action_id is not found.
    """
    for action in _load_registry():
        if action.get("id") == action_id:
            return action
    return None
