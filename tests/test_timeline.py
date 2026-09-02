"""Tests for OpenTimelineIO (.otio) editorial timeline generator for DaVinci Resolve handoff."""

from __future__ import annotations

import json
from pathlib import Path

from hawedit.boundary import Boundary
from hawedit.clip import (
    Clip,
    ClipTranscript,
    DiscoveryPath,
    Editorial,
    Output,
    Qc,
    Sv6d,
)
from hawedit.delivery import publish_delivery_bundle, publish_episode_timeline
from hawedit.timeline import (
    build_clip_markers,
    build_episode_otio_timeline,
    build_otio_timeline,
    serialize_otio,
)
from hawedit.transcripts import AsrProvenance, Word


def a_clip(
    in_ms: int = 1_000,
    out_ms: int = 31_000,
    payoff_at_ms: int | None = 25_000,
) -> Clip:
    words = (
        Word(w="سڵاو", start_ms=1_000, end_ms=1_500, conf=0.95),
        Word(w="ئەمە", start_ms=1_500, end_ms=2_000, conf=0.94),
        Word(w="تەواو.", start_ms=30_000, end_ms=31_000, conf=0.93),
    )
    boundary = Boundary(
        anchor_in_ms=in_ms,
        anchor_out_ms=out_ms,
        final_in_ms=in_ms,
        final_out_ms=out_ms,
        in_extended_by=None,
        out_extended_by=None,
        sentence_complete=True,
        confidence=0.95,
    )
    return Clip(
        clip_id="test-clip-01",
        media_id="test-media",
        media_sha256="a" * 64,
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="سڵاو ئەمە تەواو.",
            norm_ckb="سڵاو ئەمە تەواو.",
            en_aux="Hello this is complete.",
            words=words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        speaker="SPK_01",
        editorial=Editorial(
            hook_score=0.90,
            meaning_fidelity=0.94,
            misleading_edit_risk=0.05,
            cultural_landing=0.86,
            narrative_role="payoff",
            judge="gemini-2.5-pro",
            self_contained=True,
            payoff_at_ms=payoff_at_ms,
            sv6d=Sv6d(
                subject="speaker at desk [2.0s]",
                aesthetics="warm key light [2.0s]",
                camera="static medium [2.0s]",
                editing="single take [2.0s-30.0s]",
                narrative="payoff of the claim [25.0s]",
                retention="raised voice holds attention [25.0s]",
            ),
        ),
        output=Output(
            title_ckb="سەردێڕ",
            description_ckb="وەسف",
            crop_target="face_tracked",
            caption_style="word_highlight",
            durations=(30,),
        ),
        qc=Qc(
            auto_pass=True,
            flags=(),
            human_reviewed=True,
            reviewed_by="Hawa",
            reviewed_at="2026-09-02T19:00:00Z",
            reviewed_sha256="0" * 64,
        ),
    )


def test_build_clip_markers_includes_hook_and_payoff() -> None:
    clip = a_clip(in_ms=2_000, out_ms=32_000, payoff_at_ms=20_000)
    fps = 25.0
    markers = build_clip_markers(
        clip,
        fps=fps,
        punch_ins=(10_000, 15_000),
        speaker_turns=((2_000, 12_000, "SPK_01"), (12_000, 32_000, "SPK_02")),
    )

    colors = [m["color"] for m in markers]

    # Hook marker (RED)
    assert "RED" in colors
    hook = next(m for m in markers if m["color"] == "RED")
    assert hook["name"] == "Hook (0-3s)"
    assert hook["marked_range"]["start_time"]["value"] == 50.0  # 2000 ms at 25 fps = 50 frames
    assert hook["marked_range"]["duration"]["value"] == 75.0  # 3000 ms at 25 fps = 75 frames

    # Payoff marker (BLUE)
    assert "BLUE" in colors
    payoff = next(m for m in markers if m["color"] == "BLUE")
    assert payoff["name"] == "Payoff / Core Insight"
    assert payoff["marked_range"]["start_time"]["value"] == 500.0  # 20000 ms at 25 fps = 500 frames

    # Punch-In markers (YELLOW)
    yellows = [m for m in markers if m["color"] == "YELLOW"]
    assert len(yellows) == 2
    assert yellows[0]["marked_range"]["start_time"]["value"] == 250.0  # 10s at 25 fps = 250 frames

    # Speaker turn markers (CYAN)
    cyans = [m for m in markers if m["color"] == "CYAN"]
    assert len(cyans) == 2
    assert cyans[0]["name"] == "Speaker: SPK_01"
    assert cyans[1]["name"] == "Speaker: SPK_02"


def test_build_otio_timeline_schema_conformance() -> None:
    clip = a_clip(in_ms=0, out_ms=30_000)
    timeline = build_otio_timeline(
        clip=clip,
        source_media_path="ep29.mp4",
        fps=25.0,
        punch_ins=(5_000,),
    )

    assert timeline["OTIO_SCHEMA"] == "Timeline.1"
    assert timeline["name"] == "HawEdit_test-clip-01"
    assert timeline["global_start_time"]["value"] == 0.0
    assert timeline["global_start_time"]["rate"] == 25.0

    tracks = timeline["tracks"]
    assert tracks["OTIO_SCHEMA"] == "Stack.1"
    assert len(tracks["children"]) == 2

    video_track = tracks["children"][0]
    assert video_track["kind"] == "Video"
    assert len(video_track["children"]) == 1

    video_clip = video_track["children"][0]
    assert video_clip["OTIO_SCHEMA"] == "Clip.1"
    assert video_clip["source_range"]["start_time"]["value"] == 0.0
    assert video_clip["source_range"]["duration"]["value"] == 750.0  # 30s * 25fps = 750 frames
    assert video_clip["media_reference"]["target_url"] == "ep29.mp4"
    assert len(video_clip["markers"]) >= 2  # Hook + Punch-In

    audio_track = tracks["children"][1]
    assert audio_track["kind"] == "Audio"
    assert len(audio_track["children"]) == 1


def test_build_episode_otio_timeline_assembles_multiple_clips() -> None:
    clip1 = a_clip(in_ms=1_000, out_ms=10_000)
    clip2 = a_clip(in_ms=15_000, out_ms=25_000)
    episode = build_episode_otio_timeline(
        clips=[clip1, clip2],
        source_media_path="source_episode.mp4",
        fps=30.0,
        episode_title="HawEdit Episode 29",
    )

    assert episode["OTIO_SCHEMA"] == "Timeline.1"
    assert episode["name"] == "HawEdit Episode 29"
    tracks = episode["tracks"]["children"]
    video_track = tracks[0]
    assert len(video_track["children"]) == 2
    assert video_track["children"][0]["name"] == "Clip_01_test-clip-01"
    assert video_track["children"][1]["name"] == "Clip_02_test-clip-01"


def test_serialize_otio_produces_valid_json() -> None:
    clip = a_clip()
    timeline = build_otio_timeline(clip, "test.mp4", 25.0)
    serialized = serialize_otio(timeline)
    loaded = json.loads(serialized)
    assert loaded["OTIO_SCHEMA"] == "Timeline.1"
    assert loaded["name"] == "HawEdit_test-clip-01"


def test_publish_delivery_bundle_writes_all_editorial_sidecars(tmp_path: Path) -> None:
    clip = a_clip(in_ms=2_000, out_ms=32_000)
    bundle_files = publish_delivery_bundle(
        output_dir=tmp_path,
        clip=clip,
        source_media_path="ep29.mp4",
        fps=25.0,
        punch_ins=(10_000,),
    )

    assert "edl" in bundle_files
    assert "json" in bundle_files
    assert "otio" in bundle_files
    assert bundle_files["edl"].is_file() and bundle_files["edl"].stat().st_size > 0
    assert bundle_files["json"].is_file() and bundle_files["json"].stat().st_size > 0
    assert bundle_files["otio"].is_file() and bundle_files["otio"].stat().st_size > 0

    otio_content = json.loads(bundle_files["otio"].read_text(encoding="utf-8"))
    assert otio_content["OTIO_SCHEMA"] == "Timeline.1"
    assert otio_content["name"] == "HawEdit_test-clip-01"


def test_publish_episode_timeline_writes_episode_otio(tmp_path: Path) -> None:
    clip1 = a_clip(in_ms=1_000, out_ms=10_000)
    clip2 = a_clip(in_ms=15_000, out_ms=25_000)
    otio_file = publish_episode_timeline(
        output_dir=tmp_path,
        clips=[clip1, clip2],
        source_media_path="ep29.mp4",
        fps=25.0,
        episode_title="Episode 29 Master",
    )

    assert otio_file.is_file()
    assert otio_file.name == "timeline.otio"
    content = json.loads(otio_file.read_text(encoding="utf-8"))
    assert content["OTIO_SCHEMA"] == "Timeline.1"
    assert content["name"] == "Episode 29 Master"
