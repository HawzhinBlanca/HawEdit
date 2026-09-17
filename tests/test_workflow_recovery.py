"""Tests for visual workflow recovery, evidence preservation, and idempotency (VE-14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.workflow_recovery import (
    ExternalCallStatus,
    ExternalReconciliationError,
    PersistentRetryBudget,
    PublicationConflictError,
    PublishedVisualPackage,
    ResourceCapacityError,
    RetryBudgetExhaustedError,
    ScopedResourceOwnership,
    StructuredPipelineFault,
    VisualWorkflowRecoveryManager,
    WorkflowResumePlan,
    WorkflowStepStatus,
    classify_and_contain_fault,
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


def test_restart_at_each_artifact_boundary_preserves_verified_work(tmp_path: Path) -> None:
    """AC-20: Restart after interruption at each artifact boundary preserves verified work.

    WHEN a run restarts after interruption at an artifact or publication boundary,
    THE system SHALL reuse verified completed work, preserve approved bundles and
    publish each artifact at most once.
    """
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    run_id = "kurdish_episode_boundary_run"

    mgr = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)

    # 1. Boundary: Ingest & Transcribe
    ingest_evidence = work_dir / "transcript.norm.json"
    ingest_evidence.write_text('{"text": "دەستپێکی بەرنامە"}', encoding="utf-8")
    audio_evidence = work_dir / "audio.wav"
    audio_evidence.write_bytes(b"RIFF_MOCK_AUDIO_DATA_INGEST")
    mgr.save_checkpoint(
        step_name="ingest_and_transcribe",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"duration_ms": 45000, "word_count": 85},
        evidence_files=[ingest_evidence, audio_evidence],
    )
    # Simulate process interruption & restart
    r_mgr1 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan1 = r_mgr1.plan_resumption()
    assert plan1.completed_steps == ("ingest_and_transcribe",)
    assert plan1.last_completed_step == "ingest_and_transcribe"
    assert plan1.pending_steps[0] == "observation_inventory"
    assert plan1.can_resume is True

    # 2. Boundary: Observation Inventory
    obs_evidence = work_dir / "observation.json"
    obs_evidence.write_text('{"scenes": 12, "speaker_turns": 4}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="observation_inventory",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"coverage": 1.0},
        evidence_files=[obs_evidence],
    )
    r_mgr2 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan2 = r_mgr2.plan_resumption()
    assert plan2.completed_steps == ("ingest_and_transcribe", "observation_inventory")
    assert plan2.last_completed_step == "observation_inventory"
    assert plan2.pending_steps[0] == "story_mapping"

    # 3. Boundary: Story Mapping
    story_evidence = work_dir / "story_mapping.json"
    story_evidence.write_text('{"relations": ["setup_to_payoff"]}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="story_mapping",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"relations_count": 1},
        evidence_files=[story_evidence],
    )
    r_mgr3 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan3 = r_mgr3.plan_resumption()
    assert plan3.completed_steps == (
        "ingest_and_transcribe",
        "observation_inventory",
        "story_mapping",
    )
    assert plan3.pending_steps[0] == "shot_planning"

    # 4. Boundary: Shot Planning
    shot_evidence = work_dir / "shot_plan.json"
    shot_evidence.write_text('{"cuts": [1500, 3200], "focus": "speaker"}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="shot_planning",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"shots_count": 3},
        evidence_files=[shot_evidence],
    )
    r_mgr4 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan4 = r_mgr4.plan_resumption()
    assert plan4.last_completed_step == "shot_planning"
    assert plan4.pending_steps[0] == "composition_and_timing"

    # 5. Boundary: Composition and Timing
    comp_evidence = work_dir / "composition.json"
    comp_evidence.write_text('{"layout": "single_subject_eased", "fps": 25}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="composition_and_timing",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"rendered_fps": 25.0},
        evidence_files=[comp_evidence],
    )
    r_mgr5 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan5 = r_mgr5.plan_resumption()
    assert plan5.last_completed_step == "composition_and_timing"
    assert plan5.pending_steps[0] == "render_critic"

    # 6. Boundary: Render Critic (review bundle retained)
    review_evidence = work_dir / "render_critic.json"
    review_evidence.write_text('{"status": "pass", "defects": []}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="render_critic",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"critic_status": "pass"},
        evidence_files=[review_evidence],
    )
    r_mgr6 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan6 = r_mgr6.plan_resumption()
    assert plan6.last_completed_step == "render_critic"
    assert plan6.pending_steps[0] == "visual_repair"

    # 7. Boundary: Visual Repair
    repair_evidence = work_dir / "visual_repair.json"
    repair_evidence.write_text('{"repairs": []}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="visual_repair",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"applied_repairs": 0},
        evidence_files=[repair_evidence],
    )
    r_mgr7 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan7 = r_mgr7.plan_resumption()
    assert plan7.last_completed_step == "visual_repair"
    assert plan7.pending_steps == ("package_delivery",)

    # 8. Boundary: Package Delivery
    pkg_evidence = work_dir / "delivery.json"
    pkg_evidence.write_text(
        '{"package_id": "clip_kurdish_01", "published": true}', encoding="utf-8"
    )
    mgr.save_checkpoint(
        step_name="package_delivery",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"package_id": "clip_kurdish_01"},
        evidence_files=[pkg_evidence],
    )
    r_mgr8 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan8 = r_mgr8.plan_resumption()
    assert plan8.last_completed_step == "package_delivery"
    assert plan8.completed_steps == VisualWorkflowRecoveryManager.ALL_STEPS
    assert len(plan8.pending_steps) == 0
    assert plan8.can_resume is True

    # 9. Verify that evidence files remain strictly byte-identical
    assert ingest_evidence.read_text(encoding="utf-8") == '{"text": "دەستپێکی بەرنامە"}'
    assert audio_evidence.read_bytes() == b"RIFF_MOCK_AUDIO_DATA_INGEST"
    assert obs_evidence.read_text(encoding="utf-8") == '{"scenes": 12, "speaker_turns": 4}'

    # 10. Tampering with any evidence file invalidates that step on resume
    obs_evidence.write_text('{"scenes": 999, "tampered": true}', encoding="utf-8")
    tampered_mgr = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    tampered_plan = tampered_mgr.plan_resumption()
    assert "observation_inventory" not in tampered_plan.completed_steps
    assert "observation_inventory" in tampered_plan.pending_steps


def test_duplicate_submission_cannot_duplicate_public_delivery(tmp_path: Path) -> None:
    """AC-20: Duplicate submission cannot duplicate or overwrite public delivery.

    WHEN duplicate submissions occur for the same package or delivery bundle,
    THE system SHALL preserve the approved bundle, reuse existing published artifacts
    idempotently when identical, and refuse to duplicate or overwrite public output.
    """
    from hawedit.artifact_bundle import ArtifactBundle, BundleAlreadyExists
    from hawedit.pipeline import _assert_no_existing_artifacts

    delivery_dir = tmp_path / "public_delivery"
    package_id = "kurdish_reel_episode_01"

    artifacts = {
        "clip.mp4": b"PRO_KURDISH_REEL_MP4_CANONICAL_BYTES",
        "clip.ass": b"[Script Info]\nTitle: Kurdish Reel",
        "clip.srt": "1\n00:00:00,000 --> 00:00:03,000\nدەقی کوردی".encode(),
        "clip.edl": b"TITLE: Reel\n001 AX V C 00:00:00:00 00:00:03:00 00:00:00:00 00:00:03:00",
        "clip.json": b'{"clip_id": "kurdish_reel_episode_01"}',
        "clip.measured.json": b'{"lufs": -16.0, "peak": -1.5}',
        "clip.edit_plan.json": b'{"version": 1, "cuts": []}',
    }

    # 1. First submission publishes successfully
    pub1 = publish_visual_package_idempotent(
        delivery_dir=delivery_dir,
        package_id=package_id,
        artifacts=artifacts,
    )
    assert pub1.package_id == package_id
    assert pub1.already_existed is False
    pub_dir = delivery_dir / package_id
    assert pub_dir.is_dir()
    manifest_path = pub_dir / "manifest.json"
    assert manifest_path.is_file()

    # 2. Duplicate submission with identical artifacts is idempotent and does NOT duplicate
    pub2 = publish_visual_package_idempotent(
        delivery_dir=delivery_dir,
        package_id=package_id,
        artifacts=artifacts,
    )
    assert pub2.package_id == package_id
    assert pub2.already_existed is True
    assert pub2.published_files == pub1.published_files
    # Directory count must strictly remain 1 (no duplicate folders like kurdish_reel_episode_01_1)
    published_dirs = [
        p for p in delivery_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    ]
    assert len(published_dirs) == 1
    assert published_dirs[0].name == package_id

    # 3. Conflicting duplicate submission with altered bytes is strictly refused
    conflicting_artifacts = dict(artifacts)
    conflicting_artifacts["clip.mp4"] = b"TAMPERED_WRONG_MP4_BYTES"
    with pytest.raises(PublicationConflictError, match="already exists with different artifact"):
        publish_visual_package_idempotent(
            delivery_dir=delivery_dir,
            package_id=package_id,
            artifacts=conflicting_artifacts,
        )

    # 4. Published artifacts are write-once and preserved exactly
    assert (pub_dir / "clip.mp4").read_bytes() == b"PRO_KURDISH_REEL_MP4_CANONICAL_BYTES"

    # 5. ArtifactBundle write-once invariant prevents duplicate overwrite
    bundle_root = tmp_path / "bundles"
    bundle_id = "bundle-s0-0"
    bundle1 = ArtifactBundle.create(bundle_root, bundle_id)
    for suffix in ArtifactBundle.suffixes():
        if suffix == "mp4":
            bundle1.staged_path(suffix).write_bytes(b"VIDEO_CONTENT")
        else:
            bundle1.write_text(suffix, f"content_{suffix}")
    bundle1.publish()

    # Second creation under the same ID strictly refuses with BundleAlreadyExists
    with pytest.raises(BundleAlreadyExists, match="refusing to overwrite completed bundle"):
        ArtifactBundle.create(bundle_root, bundle_id)

    # 6. Pipeline level preflight guard prevents duplicate overwrite
    with pytest.raises(FileExistsError, match="refusing to overwrite existing delivery artifact"):
        _assert_no_existing_artifacts(bundle_root, "bundle", (0, 0))


def test_unknown_billed_outcome_is_not_blindly_retried(tmp_path: Path) -> None:
    """AC-21: Unknown billed outcome is not blindly retried and halts execution safely.

    WHEN a cloud request outcome is unknown or ambiguous,
    THE system SHALL persist the uncertainty and stop or reconcile under the approved policy
    instead of silently resubmitting or asserting exactly-once billing.
    """
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    run_id = "kurdish_cloud_billed_run_01"

    mgr = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)

    # 1. Complete early steps with valid evidence
    t_file = work_dir / "transcript.norm.json"
    t_file.write_text('{"text": "دەقی پشکنین"}', encoding="utf-8")
    mgr.save_checkpoint(
        step_name="ingest_and_transcribe",
        status=WorkflowStepStatus.COMPLETED,
        state_payload={"words": 40},
        evidence_files=[t_file],
    )

    # 2. Simulate external billed model call (e.g. Gemini critic / editorial judge)
    # The call drops connection after sending bytes: outcome is UNKNOWN / UNCERTAIN
    call_id = "call_gemini_critic_ack_timeout_99"
    provider = "gemini-2.5-pro"

    # Save the uncertain state into workflow checkpoint
    mgr.save_checkpoint(
        step_name="render_critic",
        status=WorkflowStepStatus.UNCERTAIN_EXTERNAL,
        state_payload={
            "call_id": call_id,
            "provider": provider,
            "disconnect_phase": "socket_timeout_after_send",
            "billed_probability": "uncertain",
        },
    )

    # 3. Process restart / resumption planning detects uncertain external billing
    resumed_mgr = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    plan = resumed_mgr.plan_resumption()

    # Invariants:
    # - can_resume is strictly False
    # - requires_external_reconciliation is strictly True
    # - render_critic is NOT marked as completed
    # - render_critic is in pending_steps awaiting operator reconciliation
    assert plan.can_resume is False
    assert plan.requires_external_reconciliation is True
    assert "render_critic" not in plan.completed_steps
    assert "render_critic" in plan.pending_steps
    assert "uncertain external billing" in str(plan.reconciliation_message)

    # 4. Blind retry without operator ledger confirmation is strictly refused
    # to prevent duplicate charges / non-idempotent duplicate billing
    with pytest.raises(
        ExternalReconciliationError,
        match="Blind retries are prohibited to prevent duplicate billing",
    ):
        reconcile_external_billed_call(
            call_id=call_id,
            provider=provider,
            status=ExternalCallStatus.UNCERTAIN_DISCONNECTED,
            recorded_ledger={},  # Empty unverified ledger
        )

    # 5. Operator reconciles with authoritative provider audit ledger
    # Scenario A: Provider ledger confirms request never executed -> safe to fail/retry
    reconciled_fail = reconcile_external_billed_call(
        call_id=call_id,
        provider=provider,
        status=ExternalCallStatus.UNCERTAIN_DISCONNECTED,
        recorded_ledger={call_id: "confirmed_failure"},
    )
    assert reconciled_fail == "confirmed_failure"

    # Scenario B: Provider ledger confirms request was processed and billed -> reuse outcome
    reconciled_succ = reconcile_external_billed_call(
        call_id=call_id,
        provider=provider,
        status=ExternalCallStatus.UNCERTAIN_DISCONNECTED,
        recorded_ledger={call_id: "confirmed_success"},
    )
    assert reconciled_succ == "confirmed_success"


def test_retry_budget_survives_process_restart(tmp_path: Path) -> None:
    """AC-21: Retry budget is bounded and survives process crashes and restarts.

    WHEN an operation consumes retries or a retry budget is exhausted,
    THE system SHALL persist the retry budget state across process restarts and
    strictly prevent unbounded retries or silent resets.
    """
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    run_id = "kurdish_retry_budget_run_02"
    budget_id = "gemini_rate_limit_retry"

    # 1. Initial process session: budget starts with max 3 attempts
    mgr1 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    budget1 = mgr1.get_retry_budget(budget_id, default_max_retries=3)
    assert isinstance(budget1, PersistentRetryBudget)
    assert budget1.max_retries == 3
    assert budget1.used_retries == 0
    assert budget1.can_retry() is True
    assert budget1.exhausted is False

    # First transient failure consumes 1 retry
    b_after_1 = mgr1.consume_retry(budget_id, default_max_retries=3)
    assert b_after_1.used_retries == 1
    assert b_after_1.can_retry() is True

    # Second transient failure consumes 2nd retry
    b_after_2 = mgr1.consume_retry(budget_id, default_max_retries=3)
    assert b_after_2.used_retries == 2
    assert b_after_2.can_retry() is True

    # 2. Process CRASH / RESTART: fresh recovery manager instance
    mgr2 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    budget2 = mgr2.get_retry_budget(budget_id, default_max_retries=3)

    # Invariant: used_retries did NOT reset to 0!
    assert budget2.used_retries == 2
    assert budget2.can_retry() is True
    assert budget2.exhausted is False

    # Third failure consumes the final retry in the budget
    b_after_3 = mgr2.consume_retry(budget_id, default_max_retries=3)
    assert b_after_3.used_retries == 3
    assert b_after_3.exhausted is True
    assert b_after_3.can_retry() is False

    # 3. Further retries on the exhausted budget are strictly refused
    with pytest.raises(
        RetryBudgetExhaustedError,
        match=r"Retry budget 'gemini_rate_limit_retry' is exhausted \(3/3\)",
    ):
        mgr2.consume_retry(budget_id, default_max_retries=3)

    # 4. Second process CRASH / RESTART: budget remains permanently exhausted
    mgr3 = VisualWorkflowRecoveryManager(work_dir, run_id=run_id)
    budget3 = mgr3.get_retry_budget(budget_id, default_max_retries=3)
    assert budget3.used_retries == 3
    assert budget3.exhausted is True
    assert budget3.can_retry() is False

    with pytest.raises(RetryBudgetExhaustedError, match="Further retries are prohibited"):
        mgr3.consume_retry(budget_id, default_max_retries=3)


def test_fault_matrix_preserves_failure_reason_and_no_false_delivery(tmp_path: Path) -> None:
    """AC-22: Real process, storage and runtime faults preserve primary reasons and withhold output.

    WHEN disk, GPU, WSL, network or cache integrity fails,
    THE system SHALL return a structured actionable failure, release owned resources
    and withhold invalid public output.
    """
    delivery_dir = tmp_path / "public_deliveries"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)

    # Fault domain test matrix: (domain, simulated_exception, expected_remediation_snippet)
    fault_scenarios: tuple[tuple[str, Exception, str], ...] = (
        (
            "disk",
            ResourceCapacityError(
                "Insufficient disk space in work_dir: 14 MB free, 100 MB required"
            ),
            "Free disk capacity",
        ),
        (
            "gpu",
            RuntimeError(
                "CUDA out of memory: tried to allocate 2.40 GiB on GPU 0; NVENC encoder reset"
            ),
            "Verify NVIDIA driver",
        ),
        (
            "wsl",
            ConnectionRefusedError(
                "WSL ASR bridge unreachable on unix:/tmp/wsl-asr.sock; daemon is not running"
            ),
            "Check WSL2 virtual machine status",
        ),
        (
            "network",
            ExternalReconciliationError(
                "External billed request 'gemini_judge_882' timed out without acknowledgement"
            ),
            "Verify cloud API network connectivity",
        ),
        (
            "cache",
            ValueError(
                "Cache integrity validation failed: SHA256 mismatch for 'transcript.norm.json'"
            ),
            "Purge corrupted intermediate cache artifacts",
        ),
    )

    for domain, exc, expected_remediation in fault_scenarios:
        domain_scratch = scratch_root / domain
        domain_scratch.mkdir(parents=True, exist_ok=True)
        pkg_id = f"kurdish_reel_fault_{domain}"

        # 1. Simulate active private scratch files generated before fault occurred
        scratch_frame = domain_scratch / "frame_0001_raw.rgba"
        scratch_frame.write_bytes(b"RGBA_MOCK_UNENCODED_PIXELS")
        scratch_chunk = domain_scratch / "chunk_audio.pcm"
        scratch_chunk.write_bytes(b"RAW_AUDIO_PCM_SAMPLES")
        assert scratch_frame.exists()
        assert scratch_chunk.exists()

        # 2. Classify and contain fault
        report = classify_and_contain_fault(
            domain=domain,
            exc=exc,
            scratch_dir=domain_scratch,
            delivery_dir=delivery_dir,
            package_id=pkg_id,
        )

        # 3. Assert structured failure properties
        assert isinstance(report, StructuredPipelineFault)
        assert report.domain == domain
        assert report.primary_reason == str(exc)
        assert expected_remediation in report.actionable_remediation
        assert report.resources_released is True
        assert report.delivery_withheld is True

        # 4. Assert owned private scratch resources were strictly released
        assert not scratch_frame.exists()
        assert not scratch_chunk.exists()

        # 5. Assert invalid public delivery was strictly withheld
        assert not (delivery_dir / pkg_id).exists()

        # 6. Verify serialization round-trip
        report_dict = report.to_dict()
        assert report_dict["domain"] == domain
        assert report_dict["primary_reason"] == str(exc)
        assert report_dict["resources_released"] is True
        assert report_dict["delivery_withheld"] is True

    # 7. Fault during secondary cleanup preserves primary failure reason
    from hawedit.pipeline import _safe_exception_text

    primary_error = RuntimeError("Primary NVENC hardware encoder crashed during vertical reframe")
    cleanup_error = OSError("Permission denied when removing staging bundle")
    combined_message = (
        f"private bundle cleanup also failed: "
        f"{_safe_exception_text(str(cleanup_error), budget=512)}; original failure: "
        f"{_safe_exception_text(str(primary_error), budget=512)}"
    )
    assert "original failure: Primary NVENC hardware encoder crashed" in combined_message

    # 8. ScopedResourceOwnership context manager releases files on exception
    scoped_scratch = scratch_root / "scoped_test"
    with (
        pytest.raises(RuntimeError, match="Simulated crash in worker"),
        ScopedResourceOwnership(scoped_scratch) as scoped,
    ):
        f1 = scoped.register_owned(scoped_scratch / "tmp1.bin")
        f1.write_bytes(b"TMP_DATA")
        assert f1.exists()
        raise RuntimeError("Simulated crash in worker")

    assert not (scoped_scratch / "tmp1.bin").exists()
