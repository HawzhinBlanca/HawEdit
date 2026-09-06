"""Tests for visual workflow recovery, evidence preservation, and idempotency (VE-14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.workflow_recovery import (
    ExternalCallStatus,
    ExternalReconciliationError,
    PublicationConflictError,
    PublishedVisualPackage,
    ResourceCapacityError,
    ScopedResourceOwnership,
    VisualWorkflowRecoveryManager,
    WorkflowResumePlan,
    WorkflowStepStatus,
    publish_visual_package_idempotent,
    reconcile_external_billed_call,
    validate_preflight_resources,
)


def test_visual_workflow_recovery_preserves_evidence_and_publication_identity(
    tmp_path: Path,
) -> None:
    """VE-14: Workflow preserves verified evidence, resource ownership, and publication identity.

    WHEN execution crashes, retries or resumes after an uncertain external outcome,
    THE system SHALL preserve verified evidence, resource ownership and publication
    idempotency without claiming exactly-once external billing.
    """
    work_dir = tmp_path / "work"
    delivery_dir = tmp_path / "delivery"
    scratch_dir = tmp_path / "scratch"

    # 1. Preflight resource validation
    validate_preflight_resources(work_dir, min_disk_free_mb=5)
    with pytest.raises(ResourceCapacityError, match="Insufficient disk space"):
        validate_preflight_resources(work_dir, min_disk_free_mb=999_999_999)

    # 2. Resource ownership cleanup on error
    with (
        pytest.raises(RuntimeError, match="Simulated crash during render"),
        ScopedResourceOwnership(scratch_dir) as scoped,
    ):
        scratch_file = scoped.register_owned(scratch_dir / "temp_render_frame.raw")
        scratch_file.write_bytes(b"temp_pixel_data")
        assert scratch_file.exists()
        raise RuntimeError("Simulated crash during render")

    # Scratch file was cleaned up cleanly on exception!
    assert not (scratch_dir / "temp_render_frame.raw").exists()

    # 3. Evidence preservation across workflow crash & resumption
    mgr = VisualWorkflowRecoveryManager(work_dir, run_id="run_kurdish_reel_01")

    # Step 1: Ingest & Transcribe completes with verified evidence
    evidence_1 = work_dir / "transcript.norm.json"
    evidence_1.write_text('{"text": "kurdish transcript"}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="ingest_and_transcribe",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"words_count": 120},
        evidence_files=[evidence_1],
    )

    # Step 2: Observation inventory completes with verified evidence
    evidence_2 = work_dir / "observation.json"
    evidence_2.write_text('{"intervals": 45}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="observation_inventory",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"coverage": 1.0},
        evidence_files=[evidence_2],
    )

    # Step 3: Crashes during story_mapping (no checkpoint written for step 3)
    # New manager instance simulates fresh process resumption after crash
    resumed_mgr = VisualWorkflowRecoveryManager(work_dir, run_id="run_kurdish_reel_01")
    resume_plan: WorkflowResumePlan = resumed_mgr.plan_resumption()

    assert resume_plan.run_id == "run_kurdish_reel_01"
    assert resume_plan.last_completed_step == "observation_inventory"
    assert resume_plan.completed_steps == ("ingest_and_transcribe", "observation_inventory")
    assert "story_mapping" in resume_plan.pending_steps
    assert resume_plan.can_resume is True
    assert resume_plan.requires_external_reconciliation is False

    # Verified evidence files on disk were strictly preserved
    assert evidence_1.exists()
    assert evidence_2.exists()

    # 4. Uncertain external billed request reconciliation (no false exactly-once claim)
    # Simulates network disconnect during Gemini critique call
    mgr.save_checkpoint(
        step_name="render_critic",
        status=WorkflowStepStatus.UNCERTAIN_EXTERNAL,
        state_payload={"call_id": "call_gemini_critic_77"},
    )
    plan_with_uncertain = mgr.plan_resumption()
    assert plan_with_uncertain.requires_external_reconciliation is True
    assert plan_with_uncertain.can_resume is False
    assert "uncertain external billing" in str(plan_with_uncertain.reconciliation_message)

    # Blind retry without verification is strictly refused
    with pytest.raises(ExternalReconciliationError, match="operator reconciliation is required"):
        reconcile_external_billed_call(
            call_id="call_gemini_critic_77",
            provider="gemini-2.5-pro",
            status=ExternalCallStatus.UNCERTAIN_DISCONNECTED,
            recorded_ledger={},  # Empty ledger = unconfirmed
        )

    # Reconciles cleanly when recorded in provider ledger
    confirmed_outcome = reconcile_external_billed_call(
        call_id="call_gemini_critic_77",
        provider="gemini-2.5-pro",
        status=ExternalCallStatus.UNCERTAIN_DISCONNECTED,
        recorded_ledger={"call_gemini_critic_77": "success"},
    )
    assert confirmed_outcome == "success"

    # 5. Publication Idempotency and Artifact Immutability
    artifacts = {
        "clip.mp4": b"video_bytes_content",
        "clip.ass": b"[Script Info]\nTitle: Kurdish",
        "clip.srt": b"1\n00:00:00,000 --> 00:00:05,000\nKurdish",
    }
    package_id = "clip_kurdish_final"

    # First publication
    pub1: PublishedVisualPackage = publish_visual_package_idempotent(
        delivery_dir=delivery_dir,
        package_id=package_id,
        artifacts=artifacts,
    )
    assert pub1.package_id == package_id
    assert pub1.already_existed is False
    assert (delivery_dir / package_id / "manifest.json").exists()

    # Second publication (idempotent replay)
    pub2: PublishedVisualPackage = publish_visual_package_idempotent(
        delivery_dir=delivery_dir,
        package_id=package_id,
        artifacts=artifacts,
    )
    assert pub2.package_id == package_id
    assert pub2.already_existed is True
    # Identical publication fingerprint
    assert pub1.published_files == pub2.published_files

    # Attempt to overwrite with conflicting bytes raises PublicationConflictError
    conflicting_artifacts = dict(artifacts)
    conflicting_artifacts["clip.mp4"] = b"tampered_different_video_bytes"
    with pytest.raises(PublicationConflictError, match="already exists with different artifact"):
        publish_visual_package_idempotent(
            delivery_dir=delivery_dir,
            package_id=package_id,
            artifacts=conflicting_artifacts,
        )
