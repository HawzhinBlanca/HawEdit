"""D-277 raw-proof consumption, fresh media checks and exact atomic publication.

ApprovalContext selects host-owned inputs, not a verified capability. No cached measurement,
QcRecord, signature receipt or Boolean grants publication authority.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypedDict

from hawedit.artifact_bundle import ArtifactBundle, BundleError
from hawedit.candidate_review import (
    REVIEW_SUFFIXES,
    CandidateReviewError,
    _canonical,
    _configuration,
    _json,
    _read,
    _snapshot,
    verify_candidate_review,
)
from hawedit.captions import ffprobe_for, verify_caption_integrity
from hawedit.clip import Clip, QcRecord
from hawedit.delivery import DeliveryRefused, reconcile_delivery
from hawedit.edit_plan import VisualEditPlan
from hawedit.measure import ClipMeasurement, probe_container
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.wsl_setup import package_digest


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """Host-selected raw evidence. Never construct from untrusted web request options."""

    packet_dir: Path
    authority_dir: Path
    revision_id: str
    producer_sha256: str
    effective_configuration: Mapping[str, object]
    ssh_keygen: str = "ssh-keygen"


class _ReviewArguments(TypedDict):
    candidate_dir: Path
    source: Path
    authority_dir: Path
    candidate_id: str
    revision_id: str
    producer_sha256: str
    effective_configuration: Mapping[str, object]
    ssh_keygen: str


def _tool_digest(path: Path) -> str:
    before = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise CandidateReviewError("Recorded media tool changed while hashing")
    return digest


def _inspect_media(mp4: Path, ass: Path, ffmpeg: Path) -> ClipMeasurement:
    # A full decode catches truncated/non-media bytes before independent sampled checks.
    decoded = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-i",
            str(mp4),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=240,
        check=False,
    )
    if decoded.returncode != 0 or len(decoded.stdout) + len(decoded.stderr) > 65536:
        raise DeliveryRefused("media_decode_failed", "fully decoded video and audio", "refused")
    # Bound even OpenCV/model-backed probes to a child lifetime, not the web/queue worker.
    script = (
        "from pathlib import Path; import sys; from hawedit.measure import measure_clip; "
        "print(measure_clip(Path(sys.argv[1]), Path(sys.argv[2]), "
        "ffmpeg=Path(sys.argv[3])).to_json())"
    )
    measured = subprocess.run(
        [sys.executable, "-c", script, str(mp4), str(ass), str(ffmpeg)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=240,
        check=False,
    )
    if measured.returncode != 0 or len(measured.stdout) > 4 * 1024 * 1024:
        raise DeliveryRefused("fresh_measurement_failed", "current decoded observations", "refused")
    return ClipMeasurement.from_dict(_json(measured.stdout))


def _measurement_claims(document: dict[str, Any]) -> bytes:
    # Filesystem location and observation time are not physical properties of the media.
    value = _json(_canonical(document))
    value["file"].pop("path", None)
    value["tool_metadata"].pop("measured_at", None)
    return _canonical(value)


def _reconcile_packet(
    staged: PrivateDirectory,
    candidate_id: str,
    source: Path,
    ffmpeg: Path,
    context: ApprovalContext,
    qc_record: QcRecord | None,
) -> None:
    clip_doc = _json(_read(staged, f"{candidate_id}.json", limit=4 * 1024 * 1024))
    clip = Clip.from_dict(clip_doc)
    clip.assert_renderable()
    if clip.qc is None or clip.qc.flags:
        raise DeliveryRefused("unresolved_qc_flags", "resolved QC flags", "unresolved")
    manifest = _json(_read(staged, "review.json"))
    if qc_record is not None and _canonical(qc_record.to_dict()) != _canonical(
        manifest["reviewer_claims"]
    ):
        raise DeliveryRefused("qc_claims_mismatch", "exact signed reviewer claims", "changed")
    plan_doc = _json(_read(staged, f"{candidate_id}.edit_plan.json", limit=4 * 1024 * 1024))
    plan = VisualEditPlan.from_dict(plan_doc)
    if _canonical(plan_doc) != _canonical(plan.to_dict()):
        raise DeliveryRefused("edit_plan_schema", "exact typed current plan", "changed schema")
    if (
        plan.version != 1
        or plan.clip_id != candidate_id
        or plan.media_id != clip.media_id
        or plan.media_sha256 != clip.media_sha256
        or plan.time_mapping.clip_in_ms != clip.in_ms
        or plan.time_mapping.clip_out_ms != clip.out_ms
        or clip.output is None
        or plan.config.caption_style.value != clip.output.caption_style
        or context.effective_configuration.get("edit") != plan.config.to_dict()
    ):
        raise DeliveryRefused("edit_plan_binding", "signed source/configuration/clock", "changed")
    plan.config.assert_valid()
    policy = context.effective_configuration.get("delivery")
    if (
        not isinstance(policy, dict)
        or set(policy) != {"fps", "captions_burned_in", "ffmpeg_sha256", "ffprobe_sha256"}
        or type(policy["fps"]) not in (int, float)
        or type(policy["captions_burned_in"]) is not bool
    ):
        raise DeliveryRefused(
            "delivery_policy_required", "typed bound production policy", "missing"
        )
    if (
        policy["fps"] != plan.config.fps
        or policy["captions_burned_in"] is not True
        or policy["ffmpeg_sha256"] != _tool_digest(ffmpeg)
        or policy["ffprobe_sha256"] != _tool_digest(ffprobe_for(ffmpeg))
    ):
        raise DeliveryRefused(
            "delivery_policy_binding", "recorded media toolchain and policy", "changed"
        )
    # Face presence/diarization labels are not evidence of a labelled speaker's identity.
    if clip.output.crop_target == "speaker_face":
        raise DeliveryRefused(
            "labelled_speaker_evidence_required", "labelled speaker association", "unavailable"
        )
    video, audio, _file = probe_container(source, ffprobe_for(ffmpeg))
    audio_duration = float(audio.get("duration", "0"))
    if not math.isfinite(audio_duration) or audio_duration <= 0:
        raise DeliveryRefused("source_audio_clock_missing", "actual source audio clock", "missing")
    audio_ms = round(audio_duration * 1000)
    source_duration = max(video.duration_ms, audio_ms)
    # Container audio may include an encoder tail beyond the last video frame. Use both
    # observed clocks, with the existing D-263 frame tolerance for their disagreement.
    source_tolerance = round(1500 / video.fps) if video.fps > 0 else 0
    if abs(audio_ms - video.duration_ms) > source_tolerance:
        raise DeliveryRefused(
            "source_av_clock_mismatch", source_tolerance, audio_ms - video.duration_ms
        )
    if clip.out_ms > source_duration or clip.in_ms < 0:
        raise DeliveryRefused("source_clock_out_of_bounds", source_duration, clip.out_ms)
    ass = staged.path / f"{candidate_id}.ass"
    verify_caption_integrity(
        ass, expected_text=clip.transcript.raw_ckb if clip.transcript else None
    )
    srt = _read(staged, f"{candidate_id}.srt", limit=4 * 1024 * 1024).decode("utf-8")
    edl = _read(staged, f"{candidate_id}.edl", limit=4 * 1024 * 1024).decode("utf-8")
    if srt.replace("\r\n", "\n") != plan.derive_srt():
        raise DeliveryRefused(
            "srt_plan_mismatch", "source-aligned plan-derived captions", "changed"
        )
    if edl.replace("\r\n", "\n") != plan.derive_edl(title=f"{clip.media_id} {candidate_id}"):
        raise DeliveryRefused("edl_plan_mismatch", "source/output plan-derived clocks", "changed")
    fresh = _inspect_media(staged.path / f"{candidate_id}.mp4", ass, ffmpeg)
    if manifest["reviewer_claims"]["seconds_watched"] * 1000 < fresh.video.duration_ms:
        raise DeliveryRefused(
            "incomplete_review_attestation", fresh.video.duration_ms, "partial watch"
        )
    cached = _json(_read(staged, f"{candidate_id}.measured.json", limit=4 * 1024 * 1024))
    if _measurement_claims(cached) != _measurement_claims(fresh.to_dict()):
        raise DeliveryRefused(
            "measurement_claims_mismatch", "fresh independent observations", "cached"
        )
    if fresh.video.fps != plan.config.fps:
        raise DeliveryRefused("output_fps_mismatch", plan.config.fps, fresh.video.fps)
    if plan.time_mapping.output_duration_ms != (
        clip.out_ms - clip.in_ms - clip.output.silence_removed_ms
    ):
        raise DeliveryRefused("edit_clock_mismatch", "retained source/output clock", "changed")
    if fresh.captions.events_count <= 0 or fresh.captions.median_contrast_ratio is None:
        raise DeliveryRefused("caption_measurement_missing", "measured captions", "unavailable")
    if fresh.captions.median_contrast_ratio < 4.5:
        raise DeliveryRefused(
            "caption_contrast_failed", ">=4.5", fresh.captions.median_contrast_ratio
        )
    cumulative = 0
    cuts = []
    for start, end in plan.time_mapping.retained_intervals_ms[:-1]:
        cumulative += end - start
        cuts.append(clip.in_ms + cumulative)
    reconcile_delivery(
        clip,
        fresh,
        captions_burned_in=True,
        fps=plan.config.fps,
        planned_punch_ins=tuple((t, 1.0) for t in plan.punch_in_ms),
        source_shot_cuts_ms=tuple(clip.in_ms + t for t in plan.shot_cuts_ms) + tuple(cuts),
        for_review=False,
        speaker_turns=plan.speaker_turns,
    )


def publish_reviewed_candidate(
    *,
    work_dir: Path,
    candidate_id: str,
    source: Path,
    ffmpeg: Path,
    approval: ApprovalContext,
    qc_record: QcRecord | None = None,
) -> tuple[Path, ...]:
    """Reopen raw proof before and after fresh checks; atomically copy reviewed bytes."""
    context = replace(
        approval, effective_configuration=_configuration(approval.effective_configuration)
    )
    if context.producer_sha256 != package_digest(Path(__file__).parent):
        raise DeliveryRefused("producer_identity_changed", "current producer package", "changed")
    arguments = _ReviewArguments(
        candidate_dir=work_dir / "review" / candidate_id,
        source=source,
        authority_dir=context.authority_dir,
        candidate_id=candidate_id,
        revision_id=context.revision_id,
        producer_sha256=context.producer_sha256,
        effective_configuration=context.effective_configuration,
        ssh_keygen=context.ssh_keygen,
    )
    bundle: ArtifactBundle | None = None
    try:
        verified = verify_candidate_review(packet_dir=context.packet_dir, **arguments)
        root = PrivateDirectory(work_dir, create=False)
        required = sum(size for _suffix, _hash, size in verified.artifacts) + 8 * 1024 * 1024
        if shutil.disk_usage(root.path).free < required:
            raise CandidateReviewError("Insufficient storage for exact signed publication")
        bundle = ArtifactBundle.create(root.path, candidate_id, proof_bearing=True)
        staged = PrivateDirectory(bundle.staging_dir, create=False)
        packet = PrivateDirectory(context.packet_dir, create=False)
        for suffix in (*REVIEW_SUFFIXES, "review.json", "review.sig"):
            name = suffix if suffix in ("review.json", "review.sig") else f"{candidate_id}.{suffix}"
            with staged.open_new_file(name) as output:
                _snapshot(
                    packet,
                    name,
                    limit=32 * 1024**3 if suffix == "mp4" else 4 * 1024 * 1024,
                    destination=output,
                )
                output.flush()
                os.fsync(output.fileno())
        staged.sync()
        if verify_candidate_review(packet_dir=staged.path, **arguments) != verified:
            raise CandidateReviewError("Publication copy changed its raw proof bindings")
        _reconcile_packet(staged, candidate_id, source, ffmpeg, context, qc_record)
        policy = context.effective_configuration["delivery"]
        if not isinstance(policy, dict) or (
            policy["ffmpeg_sha256"] != _tool_digest(ffmpeg)
            or policy["ffprobe_sha256"] != _tool_digest(ffprobe_for(ffmpeg))
        ):
            raise CandidateReviewError("Recorded media toolchain changed during measurement")
        if (
            verify_candidate_review(packet_dir=context.packet_dir, **arguments) != verified
            or verify_candidate_review(packet_dir=staged.path, **arguments) != verified
            or context.producer_sha256 != package_digest(Path(__file__).parent)
        ):
            raise CandidateReviewError("Publication context changed during fresh measurement")
        return bundle.publish()
    except (OSError, StudioStorageError, CandidateReviewError, subprocess.TimeoutExpired) as exc:
        raise DeliveryRefused(
            "authenticated_delivery_refused", "stable trusted real media", str(exc)
        ) from exc
    finally:
        if bundle is not None and bundle.staging_dir.exists():
            # Exact expected members only; retain uncertain storage instead of deleting others.
            try:
                bundle.discard()
            except BundleError as exc:
                raise DeliveryRefused(
                    "publication_storage_uncertain", "bound private staging", str(exc)
                ) from exc
