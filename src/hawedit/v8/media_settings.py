"""Host-owned non-secret paths for private source libraries and local editing models."""

from __future__ import annotations

import json
import os

from hawedit.credentials import ENV_FILE


def media_setting(name: str) -> str | None:
    env = os.environ.get("HAWEDIT_" + name.upper())
    if env:
        return env
    path = ENV_FILE.with_name("media-tools.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(data, dict):
        raise ValueError("media-tools.json must contain an object")
    value = data.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"media-tools.json expects text for {name}")
    return value
