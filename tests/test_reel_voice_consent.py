import json
from pathlib import Path

import pytest

from hawedit.v8.dubbing import _atempo_chain, dub_reel, file_digest, verify_voice_consent


def test_clone_grant_is_bound_to_render_language_evidence_and_voice(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    movie = tmp_path / "movie.mp4"
    evidence = tmp_path / "permission.txt"
    for p in (reference, movie, evidence):
        p.write_bytes(p.name.encode())
    doc = {
        "scope": "podcast-dub",
        "speaker": "test speaker",
        "confirmed_by": "test producer",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "languages": ["ar"],
        "evidence_file": evidence.name,
        "evidence_sha256": file_digest(evidence),
        "reference_sha256": file_digest(reference),
        "reel_sha256": file_digest(movie),
    }
    receipt = tmp_path / "consent.json"
    receipt.write_text(json.dumps(doc))
    verify_voice_consent(receipt, reference, movie, "ar")
    with pytest.raises(ValueError, match="language"):
        verify_voice_consent(receipt, reference, movie, "en")
    for p in (reference, movie, evidence):
        p.write_bytes(b"different asset")
        with pytest.raises(ValueError, match="match"):
            verify_voice_consent(receipt, reference, movie, "ar")
        p.write_bytes(p.name.encode())
    receipt.write_text(json.dumps({**doc, "expires_at": "2020-01-01T00:00:00Z"}))
    with pytest.raises(ValueError, match="expired"):
        verify_voice_consent(receipt, reference, movie, "ar")


def test_voice_consent_rejects_traversal_and_missing_evidence(tmp_path: Path) -> None:
    grant_dir = tmp_path / "grant"
    grant_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    reference = grant_dir / "ref.wav"
    movie = grant_dir / "reel.mp4"
    reference.write_bytes(b"ref")
    movie.write_bytes(b"reel")
    base = {
        "scope": "podcast-dub",
        "speaker": "speaker",
        "confirmed_by": "producer",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "languages": ["en"],
        "reference_sha256": file_digest(reference),
        "reel_sha256": file_digest(movie),
        "evidence_sha256": file_digest(outside),
    }
    receipt = grant_dir / "consent.json"
    for bad_path in ("../outside.txt", str(outside)):
        receipt.write_text(json.dumps({**base, "evidence_file": bad_path}))
        with pytest.raises(ValueError, match="consent directory"):
            verify_voice_consent(receipt, reference, movie, "en")
    receipt.write_text(json.dumps({**base, "evidence_file": "missing.txt"}))
    with pytest.raises(ValueError, match="match"):
        verify_voice_consent(receipt, reference, movie, "en")


def test_dub_atempo_chain_and_crlf_srt_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _atempo_chain(1.25) == "atempo=1.250000"
    assert _atempo_chain(3.0) == "atempo=2.0,atempo=1.500000"
    with pytest.raises(ValueError, match="slot duration"):
        _atempo_chain(12.0)

    movie = tmp_path / "clip.mp4"
    movie.write_bytes(b"mp4")
    srt = tmp_path / "clip.en.srt"
    srt.write_bytes(b"1\r\n00:00:01,000 --> 00:00:01,000\r\nZero\r\n\r\n")
    monkeypatch.setattr("hawedit.v8.dubbing.find_ffmpeg", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr("hawedit.v8.dubbing.probe_duration_ms", lambda *_: 5000)
    with pytest.raises(ValueError, match="does not end after"):
        dub_reel(movie, srt, "en", worker=tmp_path / "py", weights=tmp_path / "w")

    # Multi-cue CRLF Windows SRT must split cleanly into individual phrases.
    srt.write_bytes(
        b"1\r\n00:00:00,100 --> 00:00:01,000\r\nFirst line\r\n\r\n"
        b"2\r\n00:00:01,200 --> 00:00:02,000\r\nSecond line\r\n"
    )
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> None:
        req = json.loads(Path(cmd[-1]).read_text(encoding="utf-8"))
        captured.append(req["phrases"])
        raise RuntimeError("worker-reached")

    monkeypatch.setattr("hawedit.v8.dubbing.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="worker-reached"):
        dub_reel(movie, srt, "en", worker=tmp_path / "py", weights=tmp_path / "w")
    assert captured == [["First line", "Second line"]]
