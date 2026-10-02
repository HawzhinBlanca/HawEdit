"""Real-source preparation and evidence-derived views, not model/editor acceptance."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from hawedit.events import RunEvent, RunState
from hawedit.measure import measure_clip
from hawedit.studio_generation import (
    GenerationError,
    GenerationRequest,
    ProducerSelection,
    prepare_generation,
    project_events,
    project_generation_result,
)
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root
from test_web import _handle_request

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"
TOKEN = "creator-request-00000001"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


@pytest.fixture
def uploaded(tmp_path: Path) -> tuple[UploadStore, str]:
    store = UploadStore(tmp_path / "uploads")
    data = MEDIA.read_bytes()
    ticket = store.begin("external.mp4", len(data))
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    return store, source["source_id"]


def payload(source_id: str, **options: object) -> dict[str, object]:
    return {"schema": 1, "source_id": source_id, "client_token": TOKEN, "options": options}


@pytest.mark.parametrize(
    "change",
    [
        {"source": "C:/private/source.mp4"},
        {"schema": True},
        {"schema": 2},
        {"source_id": "../source.mp4"},
        {"client_token": ""},
        {"client_token": True},
        {"options": {"preset": "imaginary"}},
        {"options": {"caption_style": "rtl_highlight"}},
        {"options": {"max_clips": True}},
        {"options": {"max_clips": 4}},
        {"options": {"hook_banner": "false"}},
        {"options": {"b_roll": "C:/private/cutaway.mp4"}},
        {"options": {"qc_record": {"human_reviewed": True}}},
        {"options": {"stock_decoder": True}},
        {"options": {"hook_text": "bad\x00text"}},
    ],
)
def test_studio_rejects_paths_and_unsupported_options(change: dict[str, object]) -> None:
    request = payload("a" * 32)
    request.update(change)
    with pytest.raises(GenerationError):
        GenerationRequest.from_payload(request)


@pytest.mark.parametrize("preset", ["broadcast", "viral", "split"])
def test_studio_prepares_shared_producer_configuration(
    uploaded: tuple[UploadStore, str], tmp_path: Path, preset: str
) -> None:
    from hawedit.content_type import resolve_effective_configuration_from_args
    from hawedit.pipeline import build_parser

    store, source_id = uploaded
    request = GenerationRequest.from_payload(payload(source_id, preset=preset))
    prepared = prepare_generation(request, store, tmp_path / "job", ProducerSelection("gemini"))
    args = build_parser().parse_args(prepared.argv)
    assert args.omni_asr and args.diarize and args.visual and args.timelens
    assert args.auto_select and args.profile == "production" and args.max_clips == 3
    assert args.gemini and args.qc_record is None and not args.stock_decoder
    assert args.source == store.source(source_id)
    cfg = resolve_effective_configuration_from_args(args)
    assert prepared.effective_configuration["caption_style"] == cfg.caption_style.value
    assert prepared.effective_configuration["two_person_split"] == cfg.two_person_split
    assert cfg.preset == preset


def test_studio_prepared_identity_uses_effective_content_not_token_or_workdir(
    uploaded: tuple[UploadStore, str], tmp_path: Path
) -> None:
    store, source_id = uploaded
    provider = ProducerSelection("gemini")
    first = prepare_generation(
        GenerationRequest.from_payload(payload(source_id)), store, tmp_path / "first", provider
    )
    other_payload = payload(source_id, preset="viral", hook_banner=True)
    other_payload["client_token"] = "creator-request-00000002"
    same = prepare_generation(
        GenerationRequest.from_payload(other_payload), store, tmp_path / "second", provider
    )
    different = prepare_generation(
        GenerationRequest.from_payload(payload(source_id, preset="broadcast")),
        store,
        tmp_path / "third",
        provider,
    )
    assert first.content_sha256 == same.content_sha256
    assert first.content_sha256 != different.content_sha256
    assert first.argv != same.argv
    assert first.source_sha256 == store.describe(source_id)["sha256"]
    assert not (tmp_path / "first").exists()


def test_studio_hook_text_is_literal_and_changed_source_is_refused(
    uploaded: tuple[UploadStore, str], tmp_path: Path
) -> None:
    from hawedit.pipeline import build_parser

    store, source_id = uploaded
    request = GenerationRequest.from_payload(payload(source_id, hook_text="--stock-decoder"))
    prepared = prepare_generation(request, store, tmp_path / "job", ProducerSelection("gemini"))
    args = build_parser().parse_args(prepared.argv)
    assert args.hook_text == "--stock-decoder" and not args.stock_decoder
    store.source(source_id).write_bytes(b"changed")
    with pytest.raises(GenerationError, match="changed"):
        prepare_generation(request, store, tmp_path / "job", ProducerSelection("gemini"))


def test_studio_provider_selection_is_explicit_not_a_silent_fallback(
    uploaded: tuple[UploadStore, str], tmp_path: Path
) -> None:
    store, source_id = uploaded
    request = GenerationRequest.from_payload(payload(source_id))
    with pytest.raises(GenerationError, match="provider"):
        prepare_generation(request, store, tmp_path / "job", ProducerSelection())
    with pytest.raises(GenerationError, match="Vertex"):
        prepare_generation(request, store, tmp_path / "job", ProducerSelection("vertex"))
    from hawedit.pipeline import build_parser

    prepared = prepare_generation(
        request, store, tmp_path / "job", ProducerSelection("vertex", vertex_project="local-test")
    )
    args = build_parser().parse_args(prepared.argv)
    assert args.vertex_project == "local-test" and not args.gemini


def test_studio_preparation_hashes_source_once_and_preserves_frozen_configuration(
    uploaded: tuple[UploadStore, str], tmp_path: Path
) -> None:
    store, source_id = uploaded

    class CountingStore(UploadStore):
        reads = 0

        def source(self, source_id: str) -> Path:
            self.reads += 1
            return super().source(source_id)

    instrumented = CountingStore(store.root)
    prepared = prepare_generation(
        GenerationRequest.from_payload(payload(source_id)),
        instrumented,
        tmp_path / "job",
        ProducerSelection("gemini"),
    )
    assert instrumented.reads == 1
    view = prepared.effective_configuration
    view["caption_style"] = "changed"
    assert prepared.effective_configuration["caption_style"] == "rtl_word_highlight"
    configuration = json.loads(prepared.configuration_json)
    assert configuration["producers"]["provider"] == "gemini"
    assert configuration["pipeline_source_sha256"] and configuration["max_clips"] == 3


@pytest.fixture(scope="module")
def measured_review(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("studio-measured-review")
    folder = root / "review" / "clip-1"
    folder.mkdir(parents=True)
    media = folder / "clip-1.mp4"
    shutil.copyfile(MEDIA, media)
    measurement = measure_clip(media)
    (folder / "clip-1.measured.json").write_text(measurement.to_json(), encoding="utf-8")
    return root


def review_report(root: Path) -> dict[str, object]:
    return {
        "render": {"path": str(root / "review" / "clip-1" / "clip-1.mp4")},
        "clip": {"clip_id": "clip-1", "output": {"title_ckb": "Review"}},
        "delivery": {"skipped": True, "reason": "awaiting human review"},
    }


def test_studio_render_is_not_completed_publication(measured_review: Path) -> None:
    report = review_report(measured_review)
    result = project_generation_result(report, measured_review)
    assert result["status"] == "awaiting-review" and not result["publication_verified"]
    clip = result["clips"][0]
    # Independent ffprobe: 103 video frames / 25 fps, not the 4.161995s audio/container clock.
    assert clip["duration_s"] == 4.12
    assert clip["sha256"] and clip["hook_score"] is None
    assert clip["state"] == "awaiting-review" and clip["artifact_path"].startswith("review/")
    assert "virality_score" not in clip
    # An untrusted report's delivery claim must not authorize publication either.
    report["delivery"] = {"measured_path": "present", "approved": True}
    assert project_generation_result(report, measured_review)["status"] != "completed"


@pytest.mark.parametrize("damage", ["missing-measurement", "changed-media", "outside-root"])
def test_studio_projection_refuses_unverified_artifacts(
    measured_review: Path, tmp_path: Path, damage: str
) -> None:
    root = tmp_path / "job"
    shutil.copytree(measured_review, root)
    report = review_report(root)
    if damage == "missing-measurement":
        (root / "review" / "clip-1" / "clip-1.measured.json").unlink()
    elif damage == "changed-media":
        (root / "review" / "clip-1" / "clip-1.mp4").write_bytes(b"changed")
    else:
        report["render"] = {"path": str(MEDIA.resolve())}
    result = project_generation_result(report, root)
    assert result["status"] == "failed" and not result["publication_verified"]
    clip = result["clips"][0]
    assert clip["duration_s"] is None and clip["sha256"] is None
    assert clip["artifact_path"] is None and clip["error"]


def test_studio_episode_projection_preserves_refusals_and_partial_outcomes(
    measured_review: Path,
) -> None:
    report = {
        "episode_manifest": {
            "episode_id": "episode-1",
            "media_id": "source-1",
            "media_sha256": "a" * 64,
            "clips_count": 1,
            "total_duration_ms": 4160,
            "clips": [
                {"clip_id": "clip-1", "delivery_dir": "review/clip-1", "title_ckb": "Review"}
            ],
            "items": [
                {"candidate_id": "clip-1", "status": "pending-review"},
                {"candidate_id": "clip-2", "status": "failed", "error": "render refused"},
                {"candidate_id": "clip-3", "status": "rejected", "rejection_reason": "fidelity"},
            ],
            "reconciled": True,
        }
    }
    result = project_generation_result(report, measured_review)
    assert result["status"] == "partially-completed"
    assert len(result["outcomes"]) == 3 and len(result["clips"]) == 1
    assert result["outcomes"][2]["rejection_reason"] == "fidelity"
    assert not result["publication_verified"] and result["published_count"] == 0


def test_studio_progress_preserves_event_state() -> None:
    events = [
        RunEvent("run-1", 1, 10, "ingest", RunState.STARTED),
        RunEvent("run-1", 2, 10, "ingest", RunState.COMPLETED),
        RunEvent("run-1", 3, 10, "editorial", RunState.STARTED),
        RunEvent("run-1", 4, 10, "editorial", RunState.BILLED, model="judge", tokens=1),
        RunEvent("run-1", 5, 10, "render", RunState.SKIPPED, reason="refused"),
    ]
    view = project_events(events, attempt=2)
    assert [event["state"] for event in view["events"]] == [event.state.value for event in events]
    assert view["stages"][1]["state"] == "started"
    assert view["stages"][2]["state"] == "skipped"
    assert view["work_progress"] is None and view["attempt"] == 2
    assert view["stage_progress"] == {"finished": 2, "observed": 3}
    with pytest.raises(GenerationError, match="sequence"):
        project_events([events[1], events[0]], attempt=2)


def test_studio_valid_source_request_refuses_missing_runner_not_fake_queue(
    uploaded: tuple[UploadStore, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    store, source_id = uploaded
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    body = json.dumps(payload(source_id, preset="viral")).encode()
    request = (
        b"POST /api/repurpose HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    code, _, response = _handle_request(request)
    assert code == 503 and json.loads(response)["code"] == "studio_runner_unavailable"
    assert manager.get_all_jobs() == [] and "job_id" not in json.loads(response)
    assert (
        _handle_request(request.replace(b"Host: localhost:8080", b"Host: attacker.example"))[0]
        == 403
    )
