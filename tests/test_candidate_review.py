"""D-277 cryptographic mechanics, not editorial or release acceptance.

Keys are ephemeral and never installed as production trust. The video is actually encoded
and decoded; constructed editing metadata does not claim human speech or quality measures.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hawedit.candidate_review import (
    REVIEW_NAMESPACE,
    REVIEW_SUFFIXES,
    CandidateReviewError,
    _snapshot,
    prepare_candidate_review,
    verify_candidate_review,
)
from hawedit.captions import find_ffmpeg
from hawedit.clip import QcRecord
from hawedit.studio_private import PrivateDirectory
from studio_test_storage import make_private_directory, seed_private_file
from test_clip import a_clip


def _json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class Tools:
    key: Path
    other_key: Path
    public_key: bytes
    video: bytes
    ssh: str


@pytest.fixture(scope="module")
def tools(tmp_path_factory: pytest.TempPathFactory) -> Tools:
    root = tmp_path_factory.mktemp("candidate-review-tools") / "private"
    make_private_directory(root)
    ssh = shutil.which("ssh-keygen")
    ffmpeg = find_ffmpeg()
    assert ssh is not None, "real OpenSSH is required; absence is not a passed signature test"
    assert ffmpeg is not None, "real FFmpeg is required; absence is not a passed media test"
    for name in ("reviewer", "other"):
        result = subprocess.run(
            [ssh, "-q", "-t", "ed25519", "-N", "", "-f", str(root / name)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    video = root / "decoded.mp4"
    encoded = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x90:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    decoded = subprocess.run(
        [str(ffmpeg), "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
    assert video.stat().st_size > 1024
    return Tools(
        root / "reviewer",
        root / "other",
        (root / "reviewer.pub").read_bytes(),
        video.read_bytes(),
        ssh,
    )


@dataclass(frozen=True)
class ReviewCase:
    root: Path
    candidate: Path
    source: Path
    authority: Path
    packet: Path
    record: QcRecord
    configuration: dict[str, object]
    tools: Tools

    def prepare(self, *, record: QcRecord | None = None) -> Path:
        return prepare_candidate_review(
            candidate_dir=self.candidate,
            source=self.source,
            packet_dir=self.packet,
            authority_dir=self.authority,
            candidate_id="c-1",
            revision_id="revision-1",
            producer_sha256="a" * 64,
            effective_configuration=self.configuration,
            review=record or self.record,
        )

    def sign(self, *, key: Path | None = None, namespace: str = REVIEW_NAMESPACE) -> None:
        result = subprocess.run(
            [self.tools.ssh, "-Y", "sign", "-f", str(key or self.tools.key), "-n", namespace],
            input=(self.packet / "review.json").read_bytes(),
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        seed_private_file(self.packet / "review.sig", result.stdout)

    def verify(self, **overrides: Any) -> Any:
        arguments: dict[str, Any] = {
            "candidate_dir": self.candidate,
            "source": self.source,
            "packet_dir": self.packet,
            "authority_dir": self.authority,
            "candidate_id": "c-1",
            "revision_id": "revision-1",
            "producer_sha256": "a" * 64,
            "effective_configuration": self.configuration,
            "ssh_keygen": self.tools.ssh,
        }
        arguments.update(overrides)
        return verify_candidate_review(**arguments)


@pytest.fixture
def case(tmp_path: Path, tools: Tools) -> ReviewCase:
    root = tmp_path / "private"
    make_private_directory(root)
    candidate = root / "candidate"
    authority = root / "authority"
    make_private_directory(candidate)
    make_private_directory(authority)
    source = root / "source.mp4"
    seed_private_file(source, tools.video)
    clip = a_clip(media_sha256=hashlib.sha256(tools.video).hexdigest(), qc=None)
    sidecars = {
        "mp4": tools.video,
        "json": _json(clip.to_dict()),
        "ass": b"[Script Info]\nTitle: synthetic binding mechanics\n",
        "srt": b"1\n00:00:00,000 --> 00:00:01,000\nSynthetic test\n\n",
        "edl": b"TITLE: synthetic binding mechanics\n",
        "measured.json": _json({"kind": "unverified-cache-not-quality-evidence"}),
        "edit_plan.json": _json({"version": 1, "purpose": "synthetic binding mechanics"}),
    }
    assert set(sidecars) == set(REVIEW_SUFFIXES)
    for suffix, data in sidecars.items():
        seed_private_file(candidate / f"c-1.{suffix}", data)
    allowed = b'editor-test namespaces="' + REVIEW_NAMESPACE.encode() + b'" ' + tools.public_key
    seed_private_file(authority / "allowed_signers", allowed)
    seed_private_file(
        authority / "policy.json",
        _json(
            {
                "schema": 1,
                "namespace": REVIEW_NAMESPACE,
                "principals": ["editor-test"],
                "allowed_signers_sha256": hashlib.sha256(allowed).hexdigest(),
                "max_review_age_seconds": 86400,
            }
        ),
    )
    record = QcRecord(
        reviewer="editor-test",
        reviewed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        mp4_sha256=hashlib.sha256(tools.video).hexdigest(),
        seconds_watched=1.0,
        verdict="approved",
        notes="Synthetic cryptographic mechanics only; no editorial acceptance.",
    )
    return ReviewCase(
        root,
        candidate,
        source,
        authority,
        root / "packet",
        record,
        {"preset": "balanced", "clips": 3},
        tools,
    )


def test_real_openssh_review_approves_bound_decoded_candidate(case: ReviewCase) -> None:
    original = (case.candidate / "c-1.json").read_bytes()
    envelope = case.prepare()
    assert envelope == case.packet / "review.json"
    case.sign()
    frozen = {p.name: p.read_bytes() for p in case.packet.iterdir()}
    evidence = case.verify()
    assert evidence.principal == "editor-test"
    assert evidence.candidate_id == "c-1"
    assert evidence.revision_id == "revision-1"
    assert evidence.envelope_sha256 == hashlib.sha256(frozen["review.json"]).hexdigest()
    assert evidence.signature_sha256 == hashlib.sha256(frozen["review.sig"]).hexdigest()
    assert {p.name: p.read_bytes() for p in case.packet.iterdir()} == frozen
    assert (case.candidate / "c-1.json").read_bytes() == original
    final = json.loads(frozen["c-1.json"])
    prior = json.loads(original)
    assert final["qc"]["reviewed_sha256"] == case.record.mp4_sha256
    assert {k: v for k, v in final.items() if k != "qc"} == {
        k: v for k, v in prior.items() if k != "qc"
    }
    assert not (case.root / "c-1").exists(), "verification is not publication"


@pytest.mark.parametrize(
    "member", [f"c-1.{suffix}" for suffix in REVIEW_SUFFIXES] + ["review.json", "review.sig"]
)
def test_changed_review_binding_refuses_publication(case: ReviewCase, member: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    path = case.packet / member
    path.write_bytes(path.read_bytes() + b"\nchanged")
    with pytest.raises(CandidateReviewError):
        case.verify()


@pytest.mark.parametrize(
    "binding", ["source", "prior-plan", "configuration", "producer", "revision", "candidate"]
)
def test_review_reopens_source_and_authoritative_context(case: ReviewCase, binding: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    overrides: dict[str, object] = {}
    if binding == "source":
        case.source.write_bytes(case.tools.video + b"changed")
    elif binding == "prior-plan":
        path = case.candidate / "c-1.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif binding == "configuration":
        overrides["effective_configuration"] = {"preset": "different", "clips": 3}
    elif binding == "producer":
        overrides["producer_sha256"] = "b" * 64
    elif binding == "revision":
        overrides["revision_id"] = "revision-2"
    else:
        overrides["candidate_id"] = "c-2"
    with pytest.raises(CandidateReviewError):
        case.verify(**overrides)


@pytest.mark.parametrize(
    "damage", ["missing", "wrong-key", "wrong-namespace", "policy", "signers", "principal"]
)
def test_invalid_review_authority_refuses_publication(case: ReviewCase, damage: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    (case.packet / "review.sig").unlink()
    if damage != "missing":
        case.sign(
            key=case.tools.other_key if damage == "wrong-key" else None,
            namespace="hawedit-release-approval"
            if damage == "wrong-namespace"
            else REVIEW_NAMESPACE,
        )
    if damage in {"policy", "principal"}:
        path = case.authority / "policy.json"
        policy = json.loads(path.read_bytes())
        if damage == "principal":
            policy["principals"] = ["not-editor-test"]
        else:
            policy["max_review_age_seconds"] = 3600
        path.write_bytes(_json(policy))
    elif damage == "signers":
        path = case.authority / "allowed_signers"
        path.write_bytes(path.read_bytes() + b"# changed\n")
    with pytest.raises(CandidateReviewError):
        case.verify()


@pytest.mark.parametrize(
    "damage",
    ["boolean", "nan", "infinity", "future", "expired", "invalid-date", "rejected", "principal"],
)
def test_review_claims_are_strict_and_not_coerced(case: ReviewCase, damage: str) -> None:
    control = replace(case, packet=case.root / "control-packet")
    control.prepare()
    control.sign()
    control.verify()
    variants: dict[str, dict[str, Any]] = {
        "boolean": {"seconds_watched": True},
        "nan": {"seconds_watched": float("nan")},
        "infinity": {"seconds_watched": float("inf")},
        "future": {
            "reviewed_at": (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        "expired": {
            "reviewed_at": (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        "invalid-date": {"reviewed_at": "2026-02-30T12:00:00Z"},
        "rejected": {"verdict": "rejected"},
        "principal": {"reviewer": "editor-test\nother"},
    }
    record = replace(case.record, **variants[damage])
    with pytest.raises(CandidateReviewError):
        case.prepare(record=record)
    assert not (case.packet / "review.json").exists()


@pytest.mark.parametrize(
    "damage", ["unknown", "duplicate", "schema-bool", "size-bool", "noncanonical", "nested"]
)
def test_even_signed_malformed_envelopes_are_refused(case: ReviewCase, damage: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    (case.packet / "review.sig").unlink()
    path = case.packet / "review.json"
    envelope = json.loads(path.read_bytes())
    if damage == "unknown":
        envelope["verified"] = True
    elif damage == "schema-bool":
        envelope["schema"] = True
    elif damage == "size-bool":
        envelope["artifacts"]["mp4"]["size_bytes"] = True
    elif damage == "nested":
        envelope["producer"]["effective_configuration"] = {"option": [[[[[[[[[1]]]]]]]]]}
    data = _json(envelope)
    if damage == "duplicate":
        data = b'{"schema":1,' + data[1:]
    elif damage == "noncanonical":
        data = json.dumps(envelope, indent=2).encode()
    path.write_bytes(data)
    case.sign()
    with pytest.raises(CandidateReviewError):
        case.verify()


def test_legacy_review_metadata_stays_unverified(case: ReviewCase) -> None:
    original = (case.candidate / "c-1.json").read_bytes()
    with pytest.raises(CandidateReviewError):
        case.verify()
    assert (case.candidate / "c-1.json").read_bytes() == original
    assert not case.packet.exists()


def test_review_packet_is_exclusive_and_incomplete_packets_refuse(case: ReviewCase) -> None:
    case.prepare()
    case.sign()
    case.verify()
    with pytest.raises(CandidateReviewError):
        case.prepare()
    (case.packet / "c-1.srt").unlink()
    with pytest.raises(CandidateReviewError):
        case.verify()


def test_review_refuses_linked_source_without_repairing_owner_data(case: ReviewCase) -> None:
    linked = case.root / "linked.mp4"
    os.link(case.source, linked)
    with pytest.raises(CandidateReviewError):
        case.prepare()
    assert linked.read_bytes() == case.tools.video
    assert case.source.stat().st_nlink == 2


def test_signed_review_expires_at_consumption(case: ReviewCase) -> None:
    case.prepare()
    case.sign()
    case.verify()
    policy_path = case.authority / "policy.json"
    policy = json.loads(policy_path.read_bytes())
    policy["max_review_age_seconds"] = 1
    policy_path.write_bytes(_json(policy))
    # Resign a now-expired assertion with the actual trusted key: crypto alone is insufficient.
    envelope_path = case.packet / "review.json"
    envelope = json.loads(envelope_path.read_bytes())
    envelope["authority_policy_sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    envelope["reviewer_claims"]["reviewed_at"] = (
        datetime.now(UTC) - timedelta(seconds=5)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope_path.write_bytes(_json(envelope))
    (case.packet / "review.sig").unlink()
    case.sign()
    with pytest.raises(
        CandidateReviewError, match="Review time is future or stale under configured policy"
    ):
        case.verify()


@pytest.mark.parametrize("suffix", REVIEW_SUFFIXES)
def test_original_candidate_changes_invalidate_raw_review(case: ReviewCase, suffix: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    path = case.candidate / f"c-1.{suffix}"
    path.write_bytes(path.read_bytes() + b"\nchanged original")
    with pytest.raises(CandidateReviewError):
        case.verify()


@pytest.mark.parametrize("scope", ["packet", "authority"])
def test_review_refuses_unprivate_storage_without_repair(
    case: ReviewCase, tmp_path: Path, scope: str
) -> None:
    case.prepare()
    case.sign()
    case.verify()
    ordinary = tmp_path / "ordinary-owner-data"
    ordinary.mkdir(mode=0o755)
    original = case.packet if scope == "packet" else case.authority
    for path in original.iterdir():
        (ordinary / path.name).write_bytes(path.read_bytes())
    before_mode = ordinary.stat().st_mode
    before = {p.name: p.read_bytes() for p in ordinary.iterdir()}
    with pytest.raises(CandidateReviewError, match="storage"):
        case.verify(**{f"{scope}_dir" if scope == "packet" else "authority_dir": ordinary})
    assert ordinary.stat().st_mode == before_mode
    assert {p.name: p.read_bytes() for p in ordinary.iterdir()} == before


@pytest.mark.parametrize("damage", ["extra-member", "hardlinked-artifact", "mixed-armor"])
def test_review_rejects_unlisted_linked_or_malformed_packet(case: ReviewCase, damage: str) -> None:
    case.prepare()
    case.sign()
    case.verify()
    if damage == "extra-member":
        seed_private_file(case.packet / "unexpected.json", b"owner data preserved")
    elif damage == "hardlinked-artifact":
        os.link(case.packet / "c-1.srt", case.root / "linked-sidecar.srt")
    else:
        path = case.packet / "review.sig"
        armor = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(armor.replace(b"\n", b"\r\n", 1))
    with pytest.raises(CandidateReviewError):
        case.verify()
    if damage == "extra-member":
        assert (case.packet / "unexpected.json").read_bytes() == b"owner data preserved"


def test_review_freezing_preserves_unresolved_qc_flags(case: ReviewCase) -> None:
    path = case.candidate / "c-1.json"
    original = json.loads(path.read_bytes())
    original["qc"] = {
        "auto_pass": False,
        "flags": ["unresolved-editorial-review"],
        "human_reviewed": False,
    }
    path.write_bytes(_json(original))
    case.prepare()
    case.sign()
    case.verify()
    frozen = json.loads((case.packet / "c-1.json").read_bytes())
    assert frozen["qc"]["flags"] == ["unresolved-editorial-review"]
    assert frozen["qc"]["auto_pass"] is False
    assert json.loads(path.read_bytes())["qc"]["human_reviewed"] is False


@pytest.mark.parametrize("damage", ["credential", "depth", "nonfinite"])
def test_effective_configuration_refuses_unsafe_evidence(case: ReviewCase, damage: str) -> None:
    configuration: dict[str, object]
    if damage == "credential":
        configuration = {"provider": {"api_key": "not-a-real-key"}}
    elif damage == "depth":
        configuration = {"option": [[[[[[[[[1]]]]]]]]]}
    else:
        configuration = {"clips": float("nan")}
    with pytest.raises(CandidateReviewError):
        replace(case, configuration=configuration).prepare()
    assert not case.packet.exists()


def test_review_stream_detects_real_mid_read_mutation(case: ReviewCase) -> None:
    source = case.root / "stream.bin"
    seed_private_file(source, b"a" * (2 * 1024 * 1024))

    class MutatingSink(io.BytesIO):
        def write(self, data: Any) -> int:
            with source.open("ab") as stream:
                stream.write(b"changed while actual descriptor is open")
                stream.flush()
                os.fsync(stream.fileno())
            return super().write(data)

    with pytest.raises(CandidateReviewError, match="changed"):
        _snapshot(
            PrivateDirectory(case.root, create=False),
            source.name,
            limit=4 * 1024 * 1024,
            destination=MutatingSink(),
        )
    assert source.stat().st_size > 2 * 1024 * 1024


def test_review_sidecar_byte_bound_refuses_before_packet_creation(case: ReviewCase) -> None:
    path = case.candidate / "c-1.edl"
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    path.write_bytes(oversized)
    with pytest.raises(CandidateReviewError, match="byte bound"):
        case.prepare()
    assert path.read_bytes() == oversized
    assert not case.packet.exists()
