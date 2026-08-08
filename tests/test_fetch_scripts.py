"""Supply-chain guards on scripts that download executable/model bytes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ffmpeg_fetch_uses_an_immutable_commit_and_lfs_digest_before_unpacking() -> None:
    script = (ROOT / "scripts" / "fetch-ffmpeg.sh").read_text(encoding="utf-8")
    commit = re.search(r'^ffmpeg_bins_commit="([0-9a-f]{40})"$', script, re.MULTILINE)
    digest = re.search(r'^linux_zip_sha256="([0-9a-f]{64})"$', script, re.MULTILINE)
    assert commit is not None
    assert digest is not None
    assert "ffmpeg_bins/main/" not in script
    assert "${ffmpeg_bins_commit}/v8.0/linux.zip" in script
    assert script.index("sha256sum --check") < script.index("unzip -oq")
    assert "curl --fail" in script and "--proto '=https'" in script


def test_model_fetch_passes_a_full_revision_and_pins_its_download_client() -> None:
    script = (ROOT / "scripts" / "fetch-models.sh").read_text(encoding="utf-8")
    assert "snapshot_download(repo_id=source, revision=revision" in script
    assert '"huggingface_hub==0.36.2"' in script
