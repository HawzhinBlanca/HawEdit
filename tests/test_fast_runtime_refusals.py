"""Invalid physical inputs must refuse before expensive media work."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
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


@pytest.mark.parametrize("header", [b"\x00\x00\x00\x20ftypisom", b"\x00\x00\x00\x01ftyp"])
def test_truncated_iso_header_refuses_before_decoder_discovery(
    tmp_path: Path, header: bytes
) -> None:
    source = tmp_path / "truncated.mp4"
    source.write_bytes(header)
    work = tmp_path / "stage-zero"
    unavailable_binary = tmp_path / "absent-ffmpeg"
    with pytest.raises(IngestError, match="Source media has an incomplete ISO header"):
        ingest(source, work, ffmpeg=unavailable_binary)
    assert not work.exists()
    assert source.read_bytes() == header


def test_encoder_recovers_when_real_executable_appears(tmp_path: Path) -> None:
    original = find_ffmpeg()
    assert original is not None, "Real ffmpeg is required to prove encoder recovery"
    executable = tmp_path / original.name
    assert not executable.exists()
    assert encoder_available(Encoder.X264, executable) is False
    shutil.copyfile(original, executable)
    executable.chmod(0o700)
    assert encoder_available(Encoder.X264, executable) is True
