"""Exact isolated utility patches without model or transitive dependency drift."""

from __future__ import annotations

import hashlib
import re

import pytest

from hawedit.wsl_asr_locks import LOCKED_DISTRIBUTIONS, RUNTIME_REQUIREMENTS
from hawedit.wsl_setup import _generation_name

PATCHES = (
    ("urllib3", "2.8.0", "0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3"),
    ("werkzeug", "3.1.9", "6392e50c78460ba618e5b21f08a71f59c99ce99cdc6cf6e3dd7e6ccca8754fab"),
)
ORIGINALS = {
    "urllib3": ("2.7.0", "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897"),
    "werkzeug": ("3.1.8", "63a77fb8892bf28ebc3178683445222aa500e48ebad5ec77b0ad80f8726b1f50"),
}


@pytest.mark.parametrize(("name", "version", "digest"), PATCHES)
def test_wsl_http_security_patches_bind_exact_upstream_wheels(
    name: str, version: str, digest: str
) -> None:
    assert LOCKED_DISTRIBUTIONS[name] == version
    blocks = re.split(r"(?m)(?=^[a-z0-9-]+==)", RUNTIME_REQUIREMENTS)
    (block,) = [value for value in blocks if value.startswith(f"{name}==")]
    assert block.strip() == f"{name}=={version} \\\n    --hash=sha256:{digest}"


def test_http_security_patch_preserves_other_runtime_requirements() -> None:
    original = RUNTIME_REQUIREMENTS
    for name, version, digest in PATCHES:
        old_version, old_digest = ORIGINALS[name]
        original = original.replace(f"{name}=={version}", f"{name}=={old_version}")
        original = original.replace(digest, old_digest)
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "5e558b24e69da83e27e9ca5f49c13abdcfd03694080522e13b8688a827077e85"
    )


def test_http_security_patch_uses_a_distinct_environment_generation() -> None:
    assert _generation_name("Ubuntu") != "Ubuntu-33853eeafb05ecf1b998dc84"
