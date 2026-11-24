"""D-277 immutable review packets and detached OpenSSH authentication.

This authenticates assertions and exact bytes, not editorial quality or publication.
Consumers must reopen raw proof with their configured authority and independently decode,
measure and reconcile media. A returned receipt is deliberately not an authorization token.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from hawedit.clip import Clip, Qc, QcRecord
from hawedit.studio_private import PrivateDirectory, StudioStorageError

REVIEW_NAMESPACE = "hawedit-candidate-review"
REVIEW_SUFFIXES = ("mp4", "ass", "srt", "edl", "json", "measured.json", "edit_plan.json")
_SIDECAR_LIMIT = 4 * 1024 * 1024
_PROOF_LIMIT = 1024 * 1024
_MEDIA_LIMIT = 32 * 1024**3
_CHUNK = 1024 * 1024
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


class CandidateReviewError(RuntimeError):
    """Review proof is unavailable, changed, malformed or unauthorized."""


@dataclass(frozen=True, slots=True)
class CandidateReviewEvidence:
    """Descriptive receipt only; publication must reverify the underlying raw proof."""

    candidate_id: str
    revision_id: str
    principal: str
    envelope_sha256: str
    signature_sha256: str
    authority_policy_sha256: str
    allowed_signers_sha256: str
    artifacts: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class _Authority:
    directory: PrivateDirectory
    policy_bytes: bytes
    signers_bytes: bytes
    principals: tuple[str, ...]
    max_age: int


@contextmanager
def _storage_boundary() -> Iterator[None]:
    try:
        yield
    except (OSError, StudioStorageError, ValueError, TypeError, RecursionError) as exc:
        raise CandidateReviewError(
            "Review storage or record is unavailable, unsafe or malformed"
        ) from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _guard_json(value: object, *, depth: int = 0, budget: list[int] | None = None) -> None:
    remaining = budget if budget is not None else [10000]
    remaining[0] -= 1
    if depth > 16 or remaining[0] < 0:
        raise CandidateReviewError("Review JSON exceeds depth or item bounds")
    if isinstance(value, dict):
        if len(value) > 512 or any(type(k) is not str or len(k) > 128 for k in value):
            raise CandidateReviewError("Review JSON keys exceed their bounds")
        for child in value.values():
            _guard_json(child, depth=depth + 1, budget=remaining)
    elif isinstance(value, list):
        for child in value:
            _guard_json(child, depth=depth + 1, budget=remaining)
    elif isinstance(value, str):
        if len(value) > 65536:
            raise CandidateReviewError("Review JSON string exceeds its bound")
    elif type(value) is float:
        if not math.isfinite(value):
            raise CandidateReviewError("Review JSON refuses nonfinite numbers")
    elif value is not None and type(value) not in (bool, int):
        raise CandidateReviewError("Review JSON refuses non-JSON values")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise CandidateReviewError("Review JSON refuses duplicate keys")
        document[key] = value
    return document


def _json(data: bytes) -> dict[str, Any]:
    parsed: object = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    _guard_json(parsed)
    if not isinstance(parsed, dict):
        raise CandidateReviewError("Review record must be a JSON object")
    return cast(dict[str, Any], parsed)


def _configuration(configuration: Mapping[str, object]) -> dict[str, object]:
    # Copy through bounded canonical JSON, so callers cannot mutate nested data mid-binding.
    _guard_json(configuration)
    encoded = _canonical(configuration)
    if len(encoded) > 65536:
        raise CandidateReviewError("Effective configuration exceeds its bound")
    result = _json(encoded)

    def check(value: object, depth: int = 0) -> None:
        if depth > 8:
            raise CandidateReviewError("Effective configuration exceeds its depth bound")
        if isinstance(value, dict):
            for key, child in value.items():
                name = re.sub(r"[^a-z0-9]", "", key.lower())
                if (
                    any(
                        term in name
                        for term in ("secret", "password", "credential", "authorization", "apikey")
                    )
                    or name.endswith("token")
                    or name.startswith(
                        (
                            "tokenfile",
                            "tokenpath",
                            "accesstoken",
                            "refreshtoken",
                            "hftoken",
                            "bearertoken",
                            "authtoken",
                            "apitoken",
                            "clienttoken",
                        )
                    )
                ):
                    raise CandidateReviewError(
                        "Effective configuration must not contain credentials"
                    )
                check(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                check(child, depth + 1)

    check(result)
    return result


def _identifier(value: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise CandidateReviewError("Review requires a scoped portable candidate/revision identity")
    return value


def _digest(value: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise CandidateReviewError("Review requires an exact lowercase SHA256 binding")
    return value


def _stamp(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink


def _cross_stamp(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def _snapshot(
    directory: PrivateDirectory,
    name: str,
    *,
    limit: int,
    capture: bool = False,
    destination: BinaryIO | None = None,
) -> tuple[dict[str, object], bytes]:
    before = directory.check_file(name)
    if before.st_size <= 0 or before.st_size > limit:
        raise CandidateReviewError("Review member is empty or exceeds its byte bound")
    chunks: list[bytes] = []
    size = 0
    digest = hashlib.sha256()
    descriptor = os.open(
        directory.path / name,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        before_fd = os.fstat(stream.fileno())
        # Windows exposes different ctime semantics through stat and fstat. Compare each
        # view against itself, with common identity/size/mtime/link checks across views.
        if _cross_stamp(before_fd) != _cross_stamp(before):
            raise CandidateReviewError("Review member changed while opening")
        while data := stream.read(_CHUNK):
            size += len(data)
            if size > limit or size > before.st_size:
                raise CandidateReviewError("Review member changed or exceeded its bound")
            digest.update(data)
            if capture:
                chunks.append(data)
            if destination is not None:
                destination.write(data)
        if (
            size != before.st_size
            or _stamp(os.fstat(stream.fileno())) != _stamp(before_fd)
            or _stamp(directory.check_file(name)) != _stamp(before)
        ):
            raise CandidateReviewError("Review member changed while reading")
    directory.verify()
    return {"sha256": digest.hexdigest(), "size_bytes": size}, b"".join(chunks)


def _read(directory: PrivateDirectory, name: str, *, limit: int = _PROOF_LIMIT) -> bytes:
    return _snapshot(directory, name, limit=limit, capture=True)[1]


def _write(directory: PrivateDirectory, name: str, data: bytes) -> None:
    with directory.open_new_file(name) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory.sync()


def _authority(path: Path) -> _Authority:
    directory = PrivateDirectory(path, create=False)
    policy_bytes = _read(directory, "policy.json")
    policy = _json(policy_bytes)
    expected = {
        "schema",
        "namespace",
        "principals",
        "allowed_signers_sha256",
        "max_review_age_seconds",
    }
    if set(policy) != expected or type(policy["schema"]) is not int or policy["schema"] != 1:
        raise CandidateReviewError("Configured review authority has an unsupported schema")
    if policy["namespace"] != REVIEW_NAMESPACE:
        raise CandidateReviewError("Configured review authority has the wrong namespace")
    principals = policy["principals"]
    if (
        not isinstance(principals, list)
        or not 1 <= len(principals) <= 64
        or any(type(p) is not str or _PRINCIPAL.fullmatch(p) is None for p in principals)
        or len(set(principals)) != len(principals)
    ):
        raise CandidateReviewError("Configured review authority requires unique trusted principals")
    max_age = policy["max_review_age_seconds"]
    if type(max_age) is not int or not 1 <= max_age <= 30 * 86400:
        raise CandidateReviewError("Configured review authority requires bounded review freshness")
    signers_bytes = _read(directory, "allowed_signers")
    if _digest(policy["allowed_signers_sha256"]) != _sha(signers_bytes):
        raise CandidateReviewError("Configured allowed-signers binding changed")
    return _Authority(directory, policy_bytes, signers_bytes, tuple(principals), max_age)


def _record(data: dict[str, Any], authority: _Authority) -> QcRecord:
    if set(data) != {
        "reviewer",
        "reviewed_at",
        "mp4_sha256",
        "seconds_watched",
        "verdict",
        "notes",
    }:
        raise CandidateReviewError("Review claims have an unsupported schema")
    principal = data["reviewer"]
    if type(principal) is not str or principal not in authority.principals:
        raise CandidateReviewError("Review principal is not configured as trusted")
    watched = data["seconds_watched"]
    if type(watched) not in (int, float) or not 0 < watched <= 86400 or not math.isfinite(watched):
        raise CandidateReviewError(
            "Review watched seconds must be finite, positive and not Boolean"
        )
    when = data["reviewed_at"]
    if type(when) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", when) is None:
        raise CandidateReviewError("Review time must be an exact UTC timestamp")
    try:
        reviewed = datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CandidateReviewError("Review time is not a real calendar timestamp") from exc
    age = (datetime.now(UTC) - reviewed).total_seconds()
    if age < 0 or age > authority.max_age:
        raise CandidateReviewError("Review time is future or stale under configured policy")
    _digest(data["mp4_sha256"])
    if data["verdict"] != "approved":
        raise CandidateReviewError("Only an explicit approved review can prepare approval proof")
    if type(data["notes"]) is not str or len(data["notes"]) > 4096:
        raise CandidateReviewError("Review notes exceed their type or size bound")
    return QcRecord.from_dict(data)


def _raw_record(record: QcRecord) -> dict[str, Any]:
    # Validate before QcRecord.to_dict() can coerce a Boolean or normalize a malformed hash.
    return {
        "reviewer": record.reviewer,
        "reviewed_at": record.reviewed_at,
        "mp4_sha256": record.mp4_sha256,
        "seconds_watched": record.seconds_watched,
        "verdict": record.verdict,
        "notes": record.notes,
    }


def _bindings(
    candidate: PrivateDirectory,
    source: Path,
    candidate_id: str,
    record: QcRecord,
) -> tuple[dict[str, object], dict[str, dict[str, object]], str, bytes]:
    source_directory = PrivateDirectory(source.parent, create=False)
    source_binding, _ = _snapshot(source_directory, source.name, limit=_MEDIA_LIMIT)
    original = _read(candidate, f"{candidate_id}.json", limit=_SIDECAR_LIMIT)
    document = _json(original)
    clip = Clip.from_dict(document)
    if clip.clip_id != candidate_id or clip.media_sha256 != source_binding["sha256"]:
        raise CandidateReviewError(
            "Candidate/source identity does not match the prior editing plan"
        )
    bindings: dict[str, dict[str, object]] = {}
    for suffix in REVIEW_SUFFIXES:
        bindings[suffix] = _snapshot(
            candidate,
            f"{candidate_id}.{suffix}",
            limit=_MEDIA_LIMIT if suffix == "mp4" else _SIDECAR_LIMIT,
        )[0]
    if bindings["json"]["sha256"] != _sha(original):
        raise CandidateReviewError("Prior editing plan changed while preparing its bindings")
    if bindings["mp4"]["sha256"] != record.mp4_sha256:
        raise CandidateReviewError("Review MP4 SHA256 does not match the candidate")
    document["qc"] = Qc.from_record(
        record,
        auto_pass=clip.qc.auto_pass if clip.qc is not None else False,
        flags=clip.qc.flags if clip.qc is not None else (),
    ).to_dict()
    final_json = _canonical(document)
    bindings["json"] = {"sha256": _sha(final_json), "size_bytes": len(final_json)}
    return source_binding, bindings, _sha(original), final_json


def _manifest(
    *,
    candidate_id: str,
    revision_id: str,
    producer_sha256: str,
    configuration: dict[str, object],
    source: dict[str, object],
    artifacts: dict[str, dict[str, object]],
    prior_plan_sha256: str,
    authority: _Authority,
    record: QcRecord,
) -> dict[str, object]:
    return {
        "schema": 1,
        "namespace": REVIEW_NAMESPACE,
        "candidate_id": candidate_id,
        "revision_id": revision_id,
        "source": source,
        "producer": {
            "package_sha256": producer_sha256,
            "configuration_sha256": _sha(_canonical(configuration)),
            "effective_configuration": configuration,
        },
        "authority_policy_sha256": _sha(authority.policy_bytes),
        "prior_plan_sha256": prior_plan_sha256,
        "reviewer_claims": record.to_dict(),
        "artifacts": artifacts,
    }


def _authority_unchanged(authority: _Authority) -> None:
    if (
        _read(authority.directory, "policy.json") != authority.policy_bytes
        or _read(authority.directory, "allowed_signers") != authority.signers_bytes
    ):
        raise CandidateReviewError("Configured review authority changed during verification")


def prepare_candidate_review(
    *,
    candidate_dir: Path,
    source: Path,
    packet_dir: Path,
    authority_dir: Path,
    candidate_id: str,
    revision_id: str,
    producer_sha256: str,
    effective_configuration: Mapping[str, object],
    review: QcRecord,
) -> Path:
    """Freeze proposed final bytes privately, before a reviewer signs review.json.

    Does not sign, decode, measure or publish. Incomplete packets are retained privately and
    cannot verify; originals are never rewritten. The host, not a request, selects authority.
    """
    with _storage_boundary():
        candidate_id = _identifier(candidate_id)
        revision_id = _identifier(revision_id)
        producer_sha256 = _digest(producer_sha256)
        configuration = _configuration(effective_configuration)
        candidate = PrivateDirectory(candidate_dir, create=False)
        authority = _authority(authority_dir)
        record = _record(_raw_record(review), authority)
        source_binding, bindings, prior, final_json = _bindings(
            candidate, source, candidate_id, record
        )
        parent = PrivateDirectory(packet_dir.parent, create=False)
        required = sum(cast(int, b["size_bytes"]) for b in bindings.values()) + 8 * _SIDECAR_LIMIT
        if shutil.disk_usage(parent.path).free < required:
            raise CandidateReviewError("Insufficient storage for the immutable review packet")
        packet = parent.child(packet_dir.name, create=True, exclusive=True)
        for suffix in REVIEW_SUFFIXES:
            name = f"{candidate_id}.{suffix}"
            if suffix == "json":
                _write(packet, name, final_json)
            else:
                with packet.open_new_file(name) as output:
                    copied, _ = _snapshot(
                        candidate,
                        name,
                        limit=_MEDIA_LIMIT if suffix == "mp4" else _SIDECAR_LIMIT,
                        destination=output,
                    )
                    output.flush()
                    os.fsync(output.fileno())
                if copied != bindings[suffix]:
                    raise CandidateReviewError("Candidate changed while copying its review packet")
            if (
                _snapshot(packet, name, limit=_MEDIA_LIMIT if suffix == "mp4" else _SIDECAR_LIMIT)[
                    0
                ]
                != bindings[suffix]
            ):
                raise CandidateReviewError("Frozen review packet bytes do not match their binding")
        if _bindings(candidate, source, candidate_id, record) != (
            source_binding,
            bindings,
            prior,
            final_json,
        ):
            raise CandidateReviewError("Candidate or source changed while freezing review")
        _authority_unchanged(authority)
        manifest = _manifest(
            candidate_id=candidate_id,
            revision_id=revision_id,
            producer_sha256=producer_sha256,
            configuration=configuration,
            source=source_binding,
            artifacts=bindings,
            prior_plan_sha256=prior,
            authority=authority,
            record=record,
        )
        _write(packet, "review.json", _canonical(manifest))
        return packet.path / "review.json"


def _signature(
    packet: PrivateDirectory,
    authority: _Authority,
    envelope: bytes,
    principal: str,
    ssh_keygen: str,
) -> bytes:
    signature = _read(packet, "review.sig")
    armor = rb"-----BEGIN SSH SIGNATURE-----\n(?:[A-Za-z0-9+/=]+\n)+-----END SSH SIGNATURE-----\n"
    if not any(
        re.fullmatch(pattern, signature) for pattern in (armor, armor.replace(b"\\n", b"\\r\\n"))
    ):
        raise CandidateReviewError("Review proof must be canonical detached OpenSSH armor")
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise CandidateReviewError("OpenSSH ssh-keygen is required to verify review proof")
    parent = PrivateDirectory(packet.path.parent, create=False)
    scratch = parent.child("review-verify-" + uuid.uuid4().hex, create=True, exclusive=True)
    owned: dict[str, tuple[int, int, int]] = {}
    try:
        for name, data in (("proof.sig", signature), ("allowed_signers", authority.signers_bytes)):
            _write(scratch, name, data)
            owned[name] = scratch.member_identity(name)
        try:
            result = subprocess.run(
                [
                    executable,
                    "-Y",
                    "verify",
                    "-f",
                    str(scratch.path / "allowed_signers"),
                    "-I",
                    principal,
                    "-n",
                    REVIEW_NAMESPACE,
                    "-s",
                    str(scratch.path / "proof.sig"),
                ],
                input=envelope,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CandidateReviewError("OpenSSH review verification failed or timed out") from exc
        if (
            _read(scratch, "proof.sig") != signature
            or _read(scratch, "allowed_signers") != authority.signers_bytes
            or _read(packet, "review.sig") != signature
            or _read(packet, "review.json") != envelope
        ):
            raise CandidateReviewError("Raw review proof changed during OpenSSH verification")
        if result.returncode != 0 or len(result.stdout) + len(result.stderr) > 8192:
            raise CandidateReviewError(
                "Detached review signature, principal or namespace did not verify"
            )
    finally:
        scratch.verify()
        if {p.name for p in scratch.path.iterdir()} != set(owned):
            raise CandidateReviewError(
                "Review verification scratch storage changed; retained for inspection"
            )
        for name, identity in owned.items():
            if not scratch.remove_owned(name, identity):
                raise CandidateReviewError(
                    "Review verification snapshot changed; retained for inspection"
                )
        scratch.verify()
        scratch.path.rmdir()
        parent.verify()
    return signature


def verify_candidate_review(
    *,
    candidate_dir: Path,
    source: Path,
    packet_dir: Path,
    authority_dir: Path,
    candidate_id: str,
    revision_id: str,
    producer_sha256: str,
    effective_configuration: Mapping[str, object],
    ssh_keygen: str = "ssh-keygen",
) -> CandidateReviewEvidence:
    """Reopen proof, owner-configured authority and every expected byte/context binding.

    This receipt is not publication approval. Media reconciliation and raw-proof revalidation
    at the actual consumption boundary remain mandatory even if this function succeeded.
    """
    with _storage_boundary():
        candidate_id = _identifier(candidate_id)
        revision_id = _identifier(revision_id)
        producer_sha256 = _digest(producer_sha256)
        configuration = _configuration(effective_configuration)
        packet = PrivateDirectory(packet_dir, create=False)
        candidate = PrivateDirectory(candidate_dir, create=False)
        expected_members = {f"{candidate_id}.{s}" for s in REVIEW_SUFFIXES} | {
            "review.json",
            "review.sig",
        }
        if {p.name for p in packet.path.iterdir()} != expected_members:
            raise CandidateReviewError("Review packet is incomplete or contains unlisted members")
        authority = _authority(authority_dir)
        envelope = _read(packet, "review.json")
        document = _json(envelope)
        if type(document.get("reviewer_claims")) is not dict:
            raise CandidateReviewError("Review packet has no strict reviewer claims")
        record = _record(document["reviewer_claims"], authority)
        source_binding, bindings, prior, final_json = _bindings(
            candidate, source, candidate_id, record
        )
        manifest = _manifest(
            candidate_id=candidate_id,
            revision_id=revision_id,
            producer_sha256=producer_sha256,
            configuration=configuration,
            source=source_binding,
            artifacts=bindings,
            prior_plan_sha256=prior,
            authority=authority,
            record=record,
        )
        if envelope != _canonical(manifest):
            raise CandidateReviewError(
                "Review envelope does not match canonical authoritative context and bindings"
            )
        for suffix in REVIEW_SUFFIXES:
            if (
                _snapshot(
                    packet,
                    f"{candidate_id}.{suffix}",
                    limit=_MEDIA_LIMIT if suffix == "mp4" else _SIDECAR_LIMIT,
                )[0]
                != bindings[suffix]
            ):
                raise CandidateReviewError("Reviewed artifact bytes changed")
        signature = _signature(packet, authority, envelope, record.reviewer, ssh_keygen)
        _authority_unchanged(authority)
        # Reopen original context and frozen artifacts after the subprocess, not just before it.
        if _bindings(candidate, source, candidate_id, record) != (
            source_binding,
            bindings,
            prior,
            final_json,
        ):
            raise CandidateReviewError("Source or candidate changed during proof verification")
        for suffix in REVIEW_SUFFIXES:
            if (
                _snapshot(
                    packet,
                    f"{candidate_id}.{suffix}",
                    limit=_MEDIA_LIMIT if suffix == "mp4" else _SIDECAR_LIMIT,
                )[0]
                != bindings[suffix]
            ):
                raise CandidateReviewError("Reviewed artifact changed during proof verification")
        if {p.name for p in packet.path.iterdir()} != expected_members:
            raise CandidateReviewError("Review packet membership changed during verification")
        _record(_raw_record(record), authority)
        _authority_unchanged(authority)
        if _read(packet, "review.json") != envelope or _read(packet, "review.sig") != signature:
            raise CandidateReviewError("Raw proof changed before returning its descriptive receipt")
        return CandidateReviewEvidence(
            candidate_id=candidate_id,
            revision_id=revision_id,
            principal=record.reviewer,
            envelope_sha256=_sha(envelope),
            signature_sha256=_sha(signature),
            authority_policy_sha256=_sha(authority.policy_bytes),
            allowed_signers_sha256=_sha(authority.signers_bytes),
            artifacts=tuple(
                (s, str(bindings[s]["sha256"]), cast(int, bindings[s]["size_bytes"]))
                for s in REVIEW_SUFFIXES
            ),
        )
