"""Invalid physical inputs must refuse before expensive media work."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.ingest import IngestError, ingest
from hawedit.render import Encoder, encoder_available


def test_empty_ingest_refuses_before_decoder_discovery(tmp_path: Path) -> None:
    source = tmp_path / "empty.mp4"
    source.write_bytes(b"")
    work = tmp_path / "stage-zero"
    unavailable_binary = tmp_path / "absent-ffmpeg"
    assert not unavailable_binary.exists()
    with pytest.raises(IngestError, match="Source media is empty"):
        ingest(source, work, ffmpeg=unavailable_binary)
    assert not work.exists()
    assert source.stat().st_size == 0


def test_missing_encoder_executable_is_unavailable(tmp_path: Path) -> None:
    unavailable_binary = tmp_path / "absent-ffmpeg"
    assert not unavailable_binary.exists()
    assert encoder_available(Encoder.NVENC, unavailable_binary) is False
    assert not list(tmp_path.iterdir())
