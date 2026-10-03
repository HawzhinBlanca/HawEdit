"""Real signed test publication controls, never production trust or native acceptance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from hawedit.artifact_bundle import ArtifactBundle
from hawedit.candidate_publication import ApprovalContext
from hawedit.candidate_review import REVIEW_NAMESPACE, prepare_candidate_review
from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.clip import Clip, QcRecord
from hawedit.delivery import promote_candidate
from hawedit.edit_plan import VisualEditPlan
from hawedit.pipeline import Delivery, PipelineRun, StageSkipped
from hawedit.studio_private import PrivateDirectory
from hawedit.wsl_setup import package_digest
from studio_test_storage import make_private_directory, seed_private_file
from test_candidate_review import Tools


def review_sidecars(run: PipelineRun) -> dict[str, Path]:
    """Read the actual private namespace, with explicit refusal and completeness checks."""
    assert isinstance(run.delivery, StageSkipped)
    assert run.delivery.reason == "awaiting human review"
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    assert run.clip is not None
    root = Path(run.work_dir)
    directory = root / "review" / run.clip.clip_id
    assert Path(run.render.path) == directory / f"{run.clip.clip_id}.mp4"
    assert not (root / run.clip.clip_id).exists()
    private = PrivateDirectory(directory, create=False)
    paths = {
        suffix: directory / f"{run.clip.clip_id}.{suffix}" for suffix in ArtifactBundle.suffixes()
    }
    for path in paths.values():
        assert private.check_file(path.name).st_size > 0
    assert not list(directory.parent.glob("*.staging"))
    return paths


def private_test_source(root: Path, source: Path) -> Path:
    PrivateDirectory(root)
    copied = root / "source.mp4"
    seed_private_file(copied, source.read_bytes())
    return copied


def signed_test_delivery(run: PipelineRun, tools: Tools) -> PipelineRun:
    """Use the actual engine for a true completion control, not manufactured True flags."""
    assert isinstance(run.delivery, StageSkipped)
    assert run.delivery.reason == "awaiting human review"
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    assert run.clip is not None
    root = Path(run.work_dir)
    source = Path(run.source)
    candidate = root / "review" / run.clip.clip_id
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    plan = VisualEditPlan.from_json(
        (candidate / f"{run.clip.clip_id}.edit_plan.json").read_text(encoding="utf-8")
    )
    authority = root / "test-authority"
    make_private_directory(authority)
    signers = b'editor-test namespaces="' + REVIEW_NAMESPACE.encode() + b'" ' + tools.public_key
    seed_private_file(authority / "allowed_signers", signers)
    seed_private_file(
        authority / "policy.json",
        json.dumps(
            {
                "schema": 1,
                "namespace": REVIEW_NAMESPACE,
                "principals": ["editor-test"],
                "allowed_signers_sha256": hashlib.sha256(signers).hexdigest(),
                "max_review_age_seconds": 86400,
            }
        ).encode(),
    )
    configuration = {
        "edit": plan.config.to_dict(),
        "delivery": {
            "fps": plan.config.fps,
            "captions_burned_in": True,
            "ffmpeg_sha256": hashlib.sha256(ffmpeg.read_bytes()).hexdigest(),
            "ffprobe_sha256": hashlib.sha256(ffprobe_for(ffmpeg).read_bytes()).hexdigest(),
        },
    }
    record = QcRecord(
        reviewer="editor-test",
        reviewed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        mp4_sha256=hashlib.sha256((candidate / f"{run.clip.clip_id}.mp4").read_bytes()).hexdigest(),
        seconds_watched=run.render.measured_duration_ms / 1000,
        verdict="approved",
        notes="Test cryptographic/measured-media mechanics only; not native editorial acceptance.",
    )
    producer = package_digest(Path(__file__).resolve().parents[1] / "src/hawedit")
    packet = root / "test-review-packet"
    prepare_candidate_review(
        candidate_dir=candidate,
        source=source,
        packet_dir=packet,
        authority_dir=authority,
        candidate_id=run.clip.clip_id,
        revision_id="test-revision-1",
        producer_sha256=producer,
        effective_configuration=configuration,
        review=record,
    )
    signed = subprocess.run(
        [tools.ssh, "-Y", "sign", "-f", str(tools.key), "-n", REVIEW_NAMESPACE],
        input=(packet / "review.json").read_bytes(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert signed.returncode == 0, signed.stderr.decode(errors="replace")
    seed_private_file(packet / "review.sig", signed.stdout)
    paths = promote_candidate(
        root,
        run.clip.clip_id,
        record,
        source=source,
        ffmpeg=ffmpeg,
        fps=plan.config.fps,
        approval=ApprovalContext(
            packet_dir=packet,
            authority_dir=authority,
            revision_id="test-revision-1",
            producer_sha256=producer,
            effective_configuration=configuration,
            ssh_keygen=tools.ssh,
        ),
    )
    assert len(paths) == 9
    assert {p.name: p.read_bytes() for p in paths} == {
        p.name: p.read_bytes() for p in packet.iterdir()
    }
    final = root / run.clip.clip_id
    return replace(
        run,
        clip=Clip.from_dict(json.loads((final / f"{run.clip.clip_id}.json").read_bytes())),
        render=replace(run.render, path=str(final / f"{run.clip.clip_id}.mp4")),
        delivery=Delivery(
            srt_path=str(final / f"{run.clip.clip_id}.srt"),
            edl_path=str(final / f"{run.clip.clip_id}.edl"),
            editing_json_path=str(final / f"{run.clip.clip_id}.json"),
            measured_path=str(final / f"{run.clip.clip_id}.measured.json"),
            edit_plan_path=str(final / f"{run.clip.clip_id}.edit_plan.json"),
        ),
    )
