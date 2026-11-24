"""D-277 publication mechanics with real media; not native editorial acceptance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import test_candidate_review as review_fixtures
from hawedit.candidate_publication import ApprovalContext
from hawedit.candidate_review import prepare_candidate_review
from hawedit.captions import build_ass, ffprobe_for, find_ffmpeg
from hawedit.clip import ClipTranscript, Output, Provenance
from hawedit.delivery import DeliveryRefused, promote_candidate
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
)
from hawedit.measure import measure_clip
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word
from hawedit.wsl_setup import package_digest
from studio_test_storage import make_private_directory, seed_private_file
from test_clip import a_boundary, a_clip

tools = review_fixtures.tools
case = review_fixtures.case


def _approve(case: review_fixtures.ReviewCase) -> ApprovalContext:
    digest = package_digest(Path(__file__).resolve().parents[1] / "src/hawedit")
    prepare_candidate_review(
        candidate_dir=case.candidate,
        source=case.source,
        packet_dir=case.packet,
        authority_dir=case.authority,
        candidate_id="c-1",
        revision_id="revision-1",
        producer_sha256=digest,
        effective_configuration=case.configuration,
        review=case.record,
    )
    case.sign()
    case.verify(producer_sha256=digest)
    return ApprovalContext(
        packet_dir=case.packet,
        authority_dir=case.authority,
        revision_id="revision-1",
        producer_sha256=package_digest(Path(__file__).resolve().parents[1] / "src/hawedit"),
        effective_configuration=case.configuration,
        ssh_keygen=case.tools.ssh,
    )


def test_plain_qc_cannot_authorize_any_publication_route(
    case: review_fixtures.ReviewCase,
) -> None:
    with pytest.raises(DeliveryRefused, match="authenticated_review_required"):
        promote_candidate(case.root, "c-1", case.record, source=case.source)
    assert not (case.root / "c-1").exists()


@pytest.fixture
def publication(case: review_fixtures.ReviewCase) -> review_fixtures.ReviewCase:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    review = case.root / "review"
    candidate = review / "c-1"
    make_private_directory(review)
    make_private_directory(candidate)
    words = (Word(w="Synthetic", start_ms=0, end_ms=1200, conf=1.0),)
    sentences = (Sentence(words=words, complete=True),)
    boundary = a_boundary(anchor_in_ms=0, anchor_out_ms=2000, media_duration_ms=2000)
    clip = a_clip(
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="Synthetic",
            norm_ckb="Synthetic",
            en_aux=None,
            words=words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        ),
        output=Output(
            title_ckb="Synthetic",
            description_ckb="Mechanics only",
            crop_target="static_centre",
            caption_style="line",
            durations=(2,),
        ),
        qc=None,
        provenance=Provenance.current(profile="production"),
    )
    ass = build_ass(sentences, clip_duration_ms=2000, keyword_emphasis=False)
    seed_private_file(candidate / "c-1.ass", ass.encode())
    # Use the private directory as cwd so the FFmpeg filter never parses a Windows drive.
    encoded = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1080x1920:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-vf",
            "ass=c-1.ass",
            "-af",
            "loudnorm=I=-14:TP=-0.7:LRA=7",
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
            "c-1.mp4",
        ],
        cwd=candidate,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    video = (candidate / "c-1.mp4").read_bytes()
    # The source is a synthetic mechanics input, not reference speech or licensed corpus.
    case.source.write_bytes(video)
    clip = replace(clip, media_sha256=hashlib.sha256(video).hexdigest())
    config = EffectiveConfiguration.resolve(
        caption_style="line",
        reframe_mode="static_centre",
        silence_threshold_ms=0,
        punch_in_cadence_ms=0,
        eased_push=False,
        keyword_emphasis=False,
    )
    plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="c-1",
        media_id=clip.media_id,
        media_sha256=clip.media_sha256 or "",
        brief=EditorialBrief.default_for_content(None, duration_ms=2000),
        config=config,
        time_mapping=SourceTimeMapping.continuous(clip.in_ms, clip.out_ms),
        sentences=sentences,
    )
    measured = measure_clip(candidate / "c-1.mp4", candidate / "c-1.ass", ffmpeg=ffmpeg)
    for suffix, data in {
        "json": json.dumps(clip.to_dict(), ensure_ascii=False),
        "srt": plan.derive_srt(),
        "edl": plan.derive_edl(title=f"{clip.media_id} c-1"),
        "edit_plan.json": plan.to_json(),
        "measured.json": measured.to_json(),
    }.items():
        seed_private_file(candidate / f"c-1.{suffix}", data.encode())
    policy: dict[str, object] = {
        "fps": 25.0,
        "captions_burned_in": True,
        "ffmpeg_sha256": hashlib.sha256(ffmpeg.read_bytes()).hexdigest(),
        "ffprobe_sha256": hashlib.sha256(ffprobe_for(ffmpeg).read_bytes()).hexdigest(),
    }
    record = replace(case.record, mp4_sha256=hashlib.sha256(video).hexdigest(), seconds_watched=2)
    return replace(
        case,
        candidate=candidate,
        record=record,
        configuration={"edit": config.to_dict(), "delivery": policy},
    )


def test_signed_publication_preserves_every_reviewed_byte(
    publication: review_fixtures.ReviewCase,
) -> None:
    context = _approve(publication)
    original = {p.name: p.read_bytes() for p in publication.packet.iterdir()}
    published = promote_candidate(
        publication.root,
        "c-1",
        publication.record,
        source=publication.source,
        ffmpeg=find_ffmpeg(),
        approval=context,
    )
    assert len(published) == 9
    assert {p.name: p.read_bytes() for p in published} == original
    assert not list(publication.root.glob("*.staging"))


def test_signed_publication_retry_and_recovery_are_bound(
    publication: review_fixtures.ReviewCase,
) -> None:
    from hawedit.artifact_bundle import BundleAlreadyExists

    context = _approve(publication)
    paths = promote_candidate(
        publication.root,
        "c-1",
        publication.record,
        source=publication.source,
        ffmpeg=find_ffmpeg(),
        approval=context,
    )
    originals = {p.name: p.read_bytes() for p in paths}
    with pytest.raises(BundleAlreadyExists):
        promote_candidate(
            publication.root,
            "c-1",
            publication.record,
            source=publication.source,
            ffmpeg=find_ffmpeg(),
            approval=context,
        )
    assert {p.name: p.read_bytes() for p in paths} == originals


def _assert_publishable(case: review_fixtures.ReviewCase, context: ApprovalContext) -> None:
    """Run the real intact boundary in an isolated no-overwrite namespace before damage."""
    root = case.root / "baseline"
    make_private_directory(root)
    make_private_directory(root / "review")
    candidate = root / "review" / "c-1"
    make_private_directory(candidate)
    for path in case.candidate.iterdir():
        seed_private_file(candidate / path.name, path.read_bytes())
    paths = promote_candidate(
        root,
        "c-1",
        case.record,
        source=case.source,
        ffmpeg=find_ffmpeg(),
        approval=context,
    )
    assert len(paths) == 9
    assert {p.name: p.read_bytes() for p in paths} == {
        p.name: p.read_bytes() for p in case.packet.iterdir()
    }


def test_forged_measurement_cannot_publish_invalid_media(
    publication: review_fixtures.ReviewCase,
) -> None:
    context = _approve(publication)
    _assert_publishable(publication, context)
    invalid = b"PROMOTED_EXACT_MP4_BYTES_12345"
    (publication.candidate / "c-1.mp4").write_bytes(invalid)
    measurement_path = publication.candidate / "c-1.measured.json"
    cached = json.loads(measurement_path.read_bytes())
    cached["file"]["sha256"] = hashlib.sha256(invalid).hexdigest()
    cached["file"]["size_bytes"] = len(invalid)
    measurement_path.write_text(json.dumps(cached), encoding="utf-8")
    damaged = replace(
        publication,
        packet=publication.root / "damaged-packet",
        record=replace(publication.record, mp4_sha256=hashlib.sha256(invalid).hexdigest()),
    )
    damaged_context = _approve(damaged)
    with pytest.raises(DeliveryRefused, match="media_decode_failed"):
        promote_candidate(
            damaged.root,
            "c-1",
            damaged.record,
            source=damaged.source,
            ffmpeg=find_ffmpeg(),
            approval=damaged_context,
        )
    assert not (damaged.root / "c-1").exists()
    assert not list(damaged.root.glob("*.staging"))
    assert (damaged.candidate / "c-1.mp4").read_bytes() == invalid


@pytest.mark.parametrize(
    "member",
    [
        "c-1.mp4",
        "c-1.ass",
        "c-1.srt",
        "c-1.edl",
        "c-1.json",
        "c-1.measured.json",
        "c-1.edit_plan.json",
        "review.json",
        "review.sig",
    ],
)
def test_changed_review_binding_refuses_publication(
    publication: review_fixtures.ReviewCase,
    member: str,
) -> None:
    context = _approve(publication)
    _assert_publishable(publication, context)
    path = publication.packet / member
    path.write_bytes(path.read_bytes() + b"altered")
    with pytest.raises(DeliveryRefused, match="authenticated_delivery_refused"):
        promote_candidate(
            publication.root,
            "c-1",
            publication.record,
            source=publication.source,
            ffmpeg=find_ffmpeg(),
            approval=context,
        )
    assert not (publication.root / "c-1").exists()
    assert not list(publication.root.glob("*.staging"))


def test_signed_forged_duration_measurement_refuses_publication(
    publication: review_fixtures.ReviewCase,
) -> None:
    context = _approve(publication)
    _assert_publishable(publication, context)
    path = publication.candidate / "c-1.measured.json"
    cached = json.loads(path.read_bytes())
    cached["video"]["duration_ms"] += 1000
    path.write_text(json.dumps(cached), encoding="utf-8")
    damaged = replace(publication, packet=publication.root / "damaged-packet")
    damaged_context = _approve(damaged)
    with pytest.raises(DeliveryRefused, match="measurement_claims_mismatch"):
        promote_candidate(
            damaged.root,
            "c-1",
            damaged.record,
            source=damaged.source,
            ffmpeg=find_ffmpeg(),
            approval=damaged_context,
        )
    assert not (damaged.root / "c-1").exists()


def test_unsigned_constructed_measurements_cannot_promote_invalid_media(
    case: review_fixtures.ReviewCase,
) -> None:
    invalid = b"PROMOTED_EXACT_MP4_BYTES_12345"
    (case.candidate / "c-1.mp4").write_bytes(invalid)
    record = replace(case.record, mp4_sha256=hashlib.sha256(invalid).hexdigest())
    with pytest.raises(DeliveryRefused, match="authenticated_review_required"):
        promote_candidate(case.root, "c-1", record, source=case.source)
    assert not (case.root / "c-1").exists()


@pytest.mark.parametrize("changed", ["source", "revision", "configuration", "producer", "trust"])
def test_publication_reopens_each_host_binding(
    publication: review_fixtures.ReviewCase, changed: str
) -> None:
    context = _approve(publication)
    _assert_publishable(publication, context)
    if changed == "source":
        publication.source.write_bytes(publication.source.read_bytes() + b"changed source")
    elif changed == "revision":
        context = replace(context, revision_id="revision-2")
    elif changed == "configuration":
        context = replace(context, effective_configuration={"edit": {}, "delivery": {}})
    elif changed == "producer":
        context = replace(context, producer_sha256="f" * 64)
    else:
        (publication.authority / "allowed_signers").write_bytes(b"revoked\n")
    with pytest.raises(DeliveryRefused):
        promote_candidate(
            publication.root,
            "c-1",
            publication.record,
            source=publication.source,
            ffmpeg=find_ffmpeg(),
            approval=context,
        )
    assert not (publication.root / "c-1").exists()
    assert not list(publication.root.glob("*.staging"))


def test_partial_signed_review_cannot_authorize_full_video(
    publication: review_fixtures.ReviewCase,
) -> None:
    context = _approve(publication)
    _assert_publishable(publication, context)
    partial = replace(
        publication,
        packet=publication.root / "partial-review",
        record=replace(publication.record, seconds_watched=1),
    )
    partial_context = _approve(partial)
    with pytest.raises(DeliveryRefused, match="incomplete_review_attestation"):
        promote_candidate(
            partial.root,
            "c-1",
            partial.record,
            source=partial.source,
            ffmpeg=find_ffmpeg(),
            approval=partial_context,
        )
    assert not (partial.root / "c-1").exists()
    assert not list(partial.root.glob("*.staging"))
