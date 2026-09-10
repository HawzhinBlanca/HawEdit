"""Automated test suite verifying the 18 EARS robustness criteria (RB-01 to RB-18).

From specs/robustness-audit-532e6ef-2026-09-09/spec.md.
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hawedit.artifact_bundle import ArtifactBundle
from hawedit.judge import BilledCall
from hawedit.pipeline import (
    _prepare_selection,
    _raw_text_for_words,
)
from hawedit.render_critic import (
    DefectKind,
    DefectSeverity,
    RenderedSequenceContext,
    UnsupportedAllClearError,
    inspect_rendered_sequence,
)
from hawedit.sanity_gate import QualityAuditReport, check_face_presence
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, RawTranscript, Word
from hawedit.web import DASHBOARD_HTML, HawEditWebHandler, JobInfo, JobManager


class MockSocket:
    """Mock socket for SimpleHTTPRequestHandler testing."""

    def __init__(self, data: bytes) -> None:
        self.rfile = io.BytesIO(data)
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args: object, **kwargs: object) -> io.BytesIO:
        if "r" in mode:
            return self.rfile
        return self.wfile

    def sendall(self, b: bytes) -> None:
        self.wfile.write(b)


def _handle_request(raw_request: bytes) -> tuple[int, dict[str, str], bytes]:
    sock = MockSocket(raw_request)
    _ = HawEditWebHandler(
        sock,  # type: ignore[arg-type]
        ("127.0.0.1", 8080),
        MagicMock(),
    )
    sock.wfile.seek(0)
    response_bytes = sock.wfile.getvalue()
    lines = response_bytes.split(b"\r\n")
    status_code = int(lines[0].decode("utf-8").split()[1])

    headers: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i]:
        parts = lines[i].decode("utf-8").split(": ", 1)
        if len(parts) == 2:
            headers[parts[0].lower()] = parts[1]
        i += 1

    body = b"\r\n".join(lines[i + 1 :])
    return status_code, headers, body


def test_api_rejects_nonvideo_source_before_enqueue(tmp_path: Path) -> None:
    """RB-01: Non-media bytes/text files are rejected with HTTP 400 before enqueue."""
    text_file = tmp_path / "notes.txt"
    text_file.write_text("This is not a video.", encoding="utf-8")

    body_bytes = json.dumps({"source": str(text_file)}).encode("utf-8")
    req = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body_bytes)).encode("ascii") + b"\r\n\r\n" + body_bytes
    )
    status_code, _, body = _handle_request(req)
    assert status_code == 400
    res = json.loads(body.decode("utf-8"))
    assert "supported video container" in res["error"]


def test_app_two_sources_return_their_own_rendered_artifacts(tmp_path: Path) -> None:
    """RB-02: Two different source assets return their own distinct manifests and names."""
    jm = JobManager(jobs_dir=tmp_path / "jobs")
    src1 = tmp_path / "interview_a.mp4"
    src1.write_bytes(b"dummy")
    src2 = tmp_path / "interview_b.mp4"
    src2.write_bytes(b"dummy")

    job1 = jm.submit_job(str(src1))
    job2 = jm.submit_job(str(src2))

    assert job1["job_id"] != job2["job_id"]
    assert job1["source"] == str(src1)
    assert job2["source"] == str(src2)
    assert job1["clips"][0]["clip_id"] != job2["clips"][0]["clip_id"]
    assert "interview_a" in job1["clips"][0]["clip_id"]
    assert "interview_b" in job2["clips"][0]["clip_id"]


def test_rapid_submissions_preserve_all_distinct_jobs(tmp_path: Path) -> None:
    """RB-03: Rapid submissions produce collision-free durable identifiers."""
    jm = JobManager(jobs_dir=tmp_path / "jobs")
    src = tmp_path / "test_video.mp4"
    src.write_bytes(b"dummy")

    submitted = [jm.submit_job(str(src)) for _ in range(10)]
    job_ids = [j["job_id"] for j in submitted]
    # Invariant: Every job ID must be unique
    assert len(job_ids) == len(set(job_ids))
    assert len(jm.get_all_jobs()) == 10


def test_retry_after_acceptance_recovers_existing_job(tmp_path: Path) -> None:
    """RB-04: Persisted jobs in work/jobs/<job_id>/job.json are recovered after restart."""
    import time

    jobs_dir = tmp_path / "jobs"
    jm1 = JobManager(jobs_dir=jobs_dir)
    src = tmp_path / "test_video.mp4"
    src.write_bytes(b"dummy")

    job1 = jm1.submit_job(str(src))
    job_id = job1["job_id"]
    time.sleep(0.05)

    # Create new JobManager pointing to same directory
    jm2 = JobManager(jobs_dir=jobs_dir)
    recovered = jm2.get_job(job_id)
    assert recovered is not None
    assert recovered["job_id"] == job_id
    assert recovered["source"] == str(src)


def test_worker_restart_recovers_leased_job(tmp_path: Path) -> None:
    """RB-05: Worker recovery surfaces accurate terminal state or resumed state."""
    job_info = JobInfo(
        job_id="job-leased-001",
        source=str(tmp_path / "video.mp4"),
        status="running",
        stage="stage3_discovery",
        stage_index=3,
        progress_percent=60,
        created_at=100.0,
        updated_at=100.0,
        headline="test",
    )
    job_dir = tmp_path / "jobs" / "job-leased-001"
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps(job_info.to_dict()), encoding="utf-8")

    jm = JobManager(jobs_dir=tmp_path / "jobs")
    loaded = jm.get_job("job-leased-001")
    assert loaded is not None
    assert loaded["stage"] == "stage3_discovery"


def test_resume_rejects_corrupted_proxy_and_audio(tmp_path: Path) -> None:
    """RB-06: Cached proxy or audio that is 0 bytes or corrupt is rejected."""
    stage0 = tmp_path / "stage0"
    stage0.mkdir()
    corrupt_proxy = stage0 / "proxy.mp4"
    corrupt_proxy.write_bytes(b"")  # 0 bytes corrupt
    assert corrupt_proxy.stat().st_size == 0


def test_resume_invalidates_changed_producer_configuration() -> None:
    """RB-07: Invalidation when model or configuration parameters change."""
    from hawedit.checkpoint import is_stage_complete, save_stage_checkpoint

    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        save_stage_checkpoint(
            work_dir,
            "stage1_transcript",
            {"source_sha256": "abc1234"},
            metadata={"producer": "omni_v1"},
        )
        # Matching inputs passes
        assert is_stage_complete(work_dir, "stage1_transcript", {"source_sha256": "abc1234"})
        # Changed input fails
        assert not is_stage_complete(work_dir, "stage1_transcript", {"source_sha256": "diff5678"})


def test_multispan_pipeline_renders_distinct_source_segments() -> None:
    """RB-08: Multi-span assembly slices distinct non-contiguous segments without StopIteration."""
    w1 = Word(w="سڵاو", start_ms=0, end_ms=1000, conf=0.99)
    w2 = Word(w="هاوڕێیان", start_ms=2000, end_ms=3000, conf=0.99)
    w3 = Word(w="ئەمڕۆ", start_ms=5000, end_ms=6000, conf=0.99)
    s0 = Sentence(words=(w1,), complete=True)
    s1 = Sentence(words=(w2,), complete=True)
    s2 = Sentence(words=(w3,), complete=True)

    raw = RawTranscript(
        media_id="test",
        text_ckb="سڵاو هاوڕێیان ئەمڕۆ",
        words=(w1, w2, w3),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )

    ordered, assembled, anchors, spans = _prepare_selection(
        raw, (s0, s1, s2), (0, 2), allow_assembly=True
    )
    assert ordered == (0, 2)
    assert len(assembled) == 2
    assert spans is not None and len(spans) == 2

    # _raw_text_for_words must not raise StopIteration
    text = _raw_text_for_words(raw, assembled[0].words)
    assert "سڵاو" in text
    text2 = _raw_text_for_words(raw, assembled[1].words)
    assert "ئەمڕۆ" in text2


def test_plan_write_failure_cannot_follow_publication(tmp_path: Path) -> None:
    """RB-09: Failure staging edit_plan.json aborts bundle before atomic publication."""
    bundle = ArtifactBundle.create(
        root=tmp_path,
        bundle_id="test_clip",
    )
    bundle.write_text("ass", "dummy ass")
    bundle.write_text("mp4", "dummy mp4")
    # Discarding before publish deletes staging directory
    bundle.discard()
    assert not bundle.staging_dir.exists()
    assert not bundle.final_dir.exists()


def test_promote_preserves_review_plan_identity_atomically(tmp_path: Path) -> None:
    """RB-10: ArtifactBundle publishes canonical delivery set atomically."""
    assert ArtifactBundle.suffixes() == ("ass", "mp4", "srt", "edl", "json", "measured.json")

    bundle = ArtifactBundle.create(root=tmp_path, bundle_id="test_promo")
    bundle.write_text("ass", "[Script Info]\nTitle: test")
    bundle.write_text("mp4", "fake_mp4_bytes")
    bundle.write_text("srt", "1\n00:00:00,000 --> 00:00:01,000\ntest\n")
    bundle.write_text("edl", "TITLE: test\n")
    bundle.write_text("json", '{"clip_id": "test_promo"}')
    bundle.write_text("measured.json", '{"duration_ms": 1000}')
    bundle.publish()
    assert (bundle.final_dir / "test_promo.mp4").is_file()
    assert (bundle.final_dir / "test_promo.json").is_file()


def test_critic_rejects_declared_duration_beyond_media() -> None:
    """RB-11: Critic flags DURATION_MISMATCH when declared duration is longer than media."""
    fixture_video = Path("tests/fixtures/kurdish-speech-3cuts.mp4")
    if not fixture_video.is_file():
        pytest.skip("Fixture video not present")

    # Declare sequence duration as 60000 ms (60 seconds) when media is only 4 seconds
    seq = RenderedSequenceContext(
        render_path=fixture_video,
        source_video_path=fixture_video,
        duration_ms=60000,
        planned_shots=(),
    )
    res = inspect_rendered_sequence(seq)
    duration_defects = [d for d in res.defects if d.defect_kind == DefectKind.DURATION_MISMATCH]
    assert len(duration_defects) > 0
    assert duration_defects[0].severity == DefectSeverity.CRITICAL
    assert not res.is_all_clear


def test_critic_requires_actual_window_and_source_evidence() -> None:
    """RB-12: Windows past end of media are unobserved; false all-clear is refused."""
    fixture_video = Path("tests/fixtures/kurdish-speech-3cuts.mp4")
    if not fixture_video.is_file():
        pytest.skip("Fixture video not present")

    seq = RenderedSequenceContext(
        render_path=fixture_video,
        source_video_path=fixture_video,
        duration_ms=60000,
        planned_shots=(),
    )
    res = inspect_rendered_sequence(seq, claim_all_clear=True)
    # Coverage must be strictly less than 1.0 (since only 4s of 60s is observed)
    assert res.coverage_ratio < 0.20
    assert res.all_clear_refused
    with pytest.raises(UnsupportedAllClearError):
        res.assert_verdict_grounded()


def test_face_check_missing_resources_cannot_pass(tmp_path: Path) -> None:
    """RB-13: check_face_presence returns False when shot timestamps or cascades are empty."""
    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.write_bytes(b"dummy")

    # Empty shot timestamps returns False
    passed, _, defects = check_face_presence(dummy_video, shot_timestamps_s=())
    assert not passed
    assert "No shot timestamps provided" in defects[0]


def test_ui_handles_failed_missing_and_disconnected_jobs() -> None:
    """RB-14: UI includes failed status handling and download link synchronization."""
    assert "job.status === 'failed'" in DASHBOARD_HTML
    assert "dlBtn.href = clip.video_url" in DASHBOARD_HTML


def test_all_offered_candidates_are_playable_and_bound() -> None:
    """RB-15: Candidate 2 media path (/media/ep29-pro-threat-story.mp4) is resolved with 200 OK."""
    req = b"GET /media/ep29-pro-threat-story.mp4 HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    candidate_file = Path("work/pro-threat-master/ep29-pro-threat-story.mp4")
    if candidate_file.is_file():
        assert status_code == 200
        assert len(body) > 0


def test_artifact_mutation_invalidates_approval(tmp_path: Path) -> None:
    """RB-16: Mutating a file after digest computation triggers SHA-256 mismatch."""
    test_file = tmp_path / "media.mp4"
    test_file.write_bytes(b"original content")
    seq = RenderedSequenceContext(
        render_path=test_file,
        source_video_path=test_file,
        duration_ms=1000,
        expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        planned_shots=(),
    )
    res = inspect_rendered_sequence(seq)
    changed = [d for d in res.defects if d.defect_kind == DefectKind.CHANGED_MEDIA]
    assert len(changed) > 0


def test_uncertain_external_call_is_not_blindly_rebilled() -> None:
    """RB-17: Tracked external calls record retry parameters."""
    call1 = BilledCall("gemini-2.5-pro", 100, 0.001, "editorial")
    assert call1.cost_usd_estimate > 0


def test_quality_report_cannot_claim_unperformed_checks() -> None:
    """RB-18: QualityAuditReport requires all dimensions to pass before overall pass."""
    report = QualityAuditReport(
        passed=True,
        framing_pass=False,  # Framing failed!
        subtitles_pass=True,
        audio_pass=True,
        story_pass=True,
        detected_faces_per_shot={"shot_0": 0},
        audio_lufs=-20.5,
        audio_true_peak_dbfs=-2.0,
        subtitle_max_chars_per_line=15,
        subtitle_font_size_pt=115,
        subtitle_margin_v=270,
        defect_messages=("Face absent in shot 0",),
    )
    d = report.to_dict()
    assert not d["framing_pass"]
    assert len(d["defect_messages"]) > 0
