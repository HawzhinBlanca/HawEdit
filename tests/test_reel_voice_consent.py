import json
from pathlib import Path

import pytest

from hawedit.v8.dubbing import file_digest, verify_voice_consent


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
