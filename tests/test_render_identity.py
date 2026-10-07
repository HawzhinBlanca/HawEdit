"""Structured request identity is provenance, not approval or quality evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from hawedit.clip import Provenance
from hawedit.render_identity import render_input_digest


@dataclass(frozen=True)
class AssetSettings:
    path: Path
    opacity: float


def test_render_identity_binds_same_path_asset_bytes(tmp_path: Path) -> None:
    asset = tmp_path / "logo.bin"
    asset.write_bytes(b"original")
    inputs = {"logo": AssetSettings(asset, 0.8), "hook_text": "Headline"}
    first = render_input_digest(inputs)
    assert first == render_input_digest(dict(reversed(list(inputs.items()))))
    asset.write_bytes(b"replaced")
    assert render_input_digest(inputs) != first


def test_render_identity_binds_asset_provenance_and_font_inventory(tmp_path: Path) -> None:
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"same media")
    sidecar = tmp_path / "asset.bin.provenance.json"
    first = render_input_digest({"asset": asset})
    sidecar.write_text('{"sha256":"different"}', encoding="utf-8")
    assert render_input_digest({"asset": asset}) != first
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "a.ttf").write_bytes(b"font bytes")
    first = render_input_digest({"fonts": fonts})
    (fonts / "b.ttf").write_bytes(b"other font bytes")
    assert render_input_digest({"fonts": fonts}) != first


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf"), {1: "key"}])
def test_render_identity_refuses_unsupported_or_nonfinite_inputs(value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        render_input_digest({"bad": value})


def test_render_identity_refuses_missing_asset(tmp_path: Path) -> None:
    with pytest.raises((OSError, ValueError)):
        render_input_digest({"asset": tmp_path / "missing.mp4"})


def test_render_identity_provenance_is_optional_and_strict() -> None:
    legacy = Provenance.current()
    assert "render_request_sha256" not in legacy.to_dict()
    assert Provenance.from_dict(legacy.to_dict()) == legacy
    bound = replace(legacy, render_request_sha256="a" * 64)
    assert Provenance.from_dict(json.loads(json.dumps(bound.to_dict()))) == bound


@pytest.mark.parametrize("value", [None, True, 0, "", "A" * 64, "0" * 63, ["a" * 64]])
def test_render_identity_provenance_refuses_malformed_binding(value: object) -> None:
    document = Provenance.current().to_dict()
    document["render_request_sha256"] = value
    with pytest.raises((ValueError, TypeError), match="render_request_sha256"):
        Provenance.from_dict(document)
