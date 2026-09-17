"""Workflow recovery, evidence preservation, and publication idempotency (VE-14 / V14).

Ensures that visual workflow execution:
1. Recovers predictably from interruptions or crashes without losing verified evidence.
2. Cleans up owned private resources cleanly while preserving primary errors.
3. Enforces an explicit reconciliation policy for uncertain external billed calls
   without falsely claiming "exactly-once" external billing.
4. Guarantees publication idempotency and artifact immutability.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hawedit.atomic_fs import write_text_atomic

__all__ = [
    "ExternalCallStatus",
    "ExternalReconciliationError",
    "PersistentRetryBudget",
    "PublicationConflictError",
    "PublishedVisualPackage",
    "ResourceCapacityError",
    "RetryBudgetExhaustedError",
    "ScopedResourceOwnership",
    "VisualWorkflowCheckpoint",
    "VisualWorkflowRecoveryManager",
    "WorkflowResumePlan",
    "WorkflowStepStatus",
    "publish_visual_package_idempotent",
    "reconcile_external_billed_call",
    "validate_preflight_resources",
]


class WorkflowRecoveryError(Exception):
    """Base error for workflow recovery and persistence failures."""


class ResourceCapacityError(WorkflowRecoveryError):
    """Raised when disk capacity or preflight checks fail before execution."""


class PublicationConflictError(WorkflowRecoveryError):
    """Raised when an attempt is made to overwrite an existing publication with different bytes."""


class ExternalReconciliationError(WorkflowRecoveryError):
    """Raised when an uncertain external billed request requires explicit operator review."""


class RetryBudgetExhaustedError(WorkflowRecoveryError):
    """Raised when an operation has exhausted its persistent retry budget."""


class WorkflowStepStatus(str, Enum):
    """Execution status of an individual workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNCERTAIN_EXTERNAL = "uncertain_external"
    RECOVERED = "recovered"


class ExternalCallStatus(str, Enum):
    """Outcome status of an external billed hosted model call."""

    CONFIRMED_SUCCESS = "confirmed_success"
    CONFIRMED_FAILURE = "confirmed_failure"
    UNCERTAIN_DISCONNECTED = "uncertain_disconnected"


@dataclass(frozen=True, slots=True)
class VisualWorkflowCheckpoint:
    """Persistent audit checkpoint of a completed visual workflow step."""

    step_name: str
    status: WorkflowStepStatus
    state_payload: dict[str, Any]
    evidence_hashes: dict[str, str]
    timestamp_iso: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status.value,
            "state_payload": self.state_payload,
            "evidence_hashes": self.evidence_hashes,
            "timestamp_iso": self.timestamp_iso,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualWorkflowCheckpoint:
        return cls(
            step_name=str(data["step_name"]),
            status=WorkflowStepStatus(str(data["status"])),
            state_payload=dict(data.get("state_payload", {})),
            evidence_hashes=dict(data.get("evidence_hashes", {})),
            timestamp_iso=str(data["timestamp_iso"]),
        )


@dataclass(frozen=True, slots=True)
class PersistentRetryBudget:
    """Persistent retry budget that survives process crashes and restarts."""

    budget_id: str
    max_retries: int
    used_retries: int = 0
    exhausted: bool = False

    def can_retry(self) -> bool:
        return not self.exhausted and self.used_retries < self.max_retries

    def record_attempt(self) -> PersistentRetryBudget:
        if self.exhausted or self.used_retries >= self.max_retries:
            raise RetryBudgetExhaustedError(
                f"Retry budget '{self.budget_id}' is exhausted "
                f"({self.used_retries}/{self.max_retries}). "
                "Further retries are prohibited to prevent unbounded cloud spend."
            )
        new_used = self.used_retries + 1
        return PersistentRetryBudget(
            budget_id=self.budget_id,
            max_retries=self.max_retries,
            used_retries=new_used,
            exhausted=new_used >= self.max_retries,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "max_retries": self.max_retries,
            "used_retries": self.used_retries,
            "exhausted": self.exhausted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersistentRetryBudget:
        return cls(
            budget_id=str(data["budget_id"]),
            max_retries=int(data["max_retries"]),
            used_retries=int(data["used_retries"]),
            exhausted=bool(data.get("exhausted", False)),
        )


@dataclass(frozen=True, slots=True)
class WorkflowResumePlan:
    """Deterministic resumption plan identifying completed steps and next action."""

    run_id: str
    last_completed_step: str | None
    completed_steps: tuple[str, ...]
    pending_steps: tuple[str, ...]
    can_resume: bool
    requires_external_reconciliation: bool
    reconciliation_message: str | None = None


@dataclass(frozen=True, slots=True)
class PublishedVisualPackage:
    """Immutable, content-addressed delivery record of a published visual package."""

    package_id: str
    destination_dir: str
    published_files: dict[str, str]  # filename -> sha256
    already_existed: bool


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_preflight_resources(
    work_dir: Path,
    min_disk_free_mb: int = 100,
) -> None:
    """Verifies preflight resource availability and disk write capacity.

    Raises:
        ResourceCapacityError: If disk capacity is lower than requested minimum.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    total, _used, free = shutil.disk_usage(work_dir)
    free_mb = free // (1024 * 1024)
    if free_mb < min_disk_free_mb:
        raise ResourceCapacityError(
            f"Insufficient disk space in {work_dir}: {free_mb} MB free, "
            f"minimum {min_disk_free_mb} MB required"
        )

    # Test probe write to ensure directory is writable
    probe = work_dir / ".probe_write.tmp"
    try:
        probe.write_text("probe", encoding="utf-8")
    except OSError as exc:
        raise ResourceCapacityError(f"Cannot write to work_dir {work_dir}: {exc}") from exc
    finally:
        if probe.exists():
            probe.unlink(missing_ok=True)


class ScopedResourceOwnership:
    """Context manager ensuring cleanup of private scratch resources on exception."""

    def __init__(self, scratch_dir: Path) -> None:
        self.scratch_dir = scratch_dir
        self._owned_files: list[Path] = []

    def register_owned(self, path: Path) -> Path:
        self._owned_files.append(path)
        return path

    def __enter__(self) -> ScopedResourceOwnership:
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            # Clean up all owned scratch files on failure while preserving the exception
            for f in self._owned_files:
                if f.is_file():
                    f.unlink(missing_ok=True)
                elif f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)


def reconcile_external_billed_call(
    call_id: str,
    provider: str,
    status: ExternalCallStatus,
    recorded_ledger: dict[str, str] | None = None,
) -> str:
    """Enforces explicit reconciliation for uncertain external billed requests.

    Strict Invariant: Does NOT blindly retry or falsely claim 'exactly-once' billing.
    If a billed request disconnected with an uncertain outcome:
    - Checks whether provider ledger has verified confirmation.
    - If unverified, raises ExternalReconciliationError requiring operator review.
    """
    if status == ExternalCallStatus.CONFIRMED_SUCCESS:
        return "success"
    if status == ExternalCallStatus.CONFIRMED_FAILURE:
        return "failed"

    # Status is UNCERTAIN_DISCONNECTED:
    if recorded_ledger and call_id in recorded_ledger:
        return recorded_ledger[call_id]

    raise ExternalReconciliationError(
        f"External billed request '{call_id}' to {provider} has uncertain status. "
        "Blind retries are prohibited to prevent duplicate billing; "
        "operator reconciliation is required."
    )


def publish_visual_package_idempotent(
    delivery_dir: Path,
    package_id: str,
    artifacts: Mapping[str, bytes],
) -> PublishedVisualPackage:
    """Atomically publishes delivered visual artifacts with strict publication idempotency.

    Invariants:
    1. If already published with identical content: returns existing package idempotently.
    2. If destination exists with conflicting contents: raises PublicationConflictError.
    3. Writes to a private staging directory and renames atomically to prevent partial writes.
    """
    dest_dir = delivery_dir / package_id
    artifact_hashes: dict[str, str] = {}
    for name, content in sorted(artifacts.items()):
        artifact_hashes[name] = _sha256_bytes(content)

    # Check if already published
    if dest_dir.exists():
        manifest_path = dest_dir / "manifest.json"
        if manifest_path.exists():
            existing_hashes: dict[str, str] = {}
            for name in artifacts:
                f_path = dest_dir / name
                if f_path.exists():
                    existing_hashes[name] = _sha256_file(f_path)

            if existing_hashes == artifact_hashes:
                return PublishedVisualPackage(
                    package_id=package_id,
                    destination_dir=str(dest_dir),
                    published_files=artifact_hashes,
                    already_existed=True,
                )
            raise PublicationConflictError(
                f"Cannot publish package '{package_id}': destination {dest_dir} already exists "
                "with different artifact bytes."
            )

    # Stage privately
    pkg_hash = hashlib.sha256(package_id.encode()).hexdigest()[:8]
    staging_dir = delivery_dir / f".staging_{package_id}_{pkg_hash}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        for name, content in artifacts.items():
            out_file = staging_dir / name
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(content)

        manifest = {
            "package_id": package_id,
            "artifacts": artifact_hashes,
        }
        (staging_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Atomic publication: rename staging to dest
        staging_dir.rename(dest_dir)
    except Exception as exc:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise WorkflowRecoveryError(
            f"Failed to publish visual package '{package_id}': {exc}"
        ) from exc

    return PublishedVisualPackage(
        package_id=package_id,
        destination_dir=str(dest_dir),
        published_files=artifact_hashes,
        already_existed=False,
    )


class VisualWorkflowRecoveryManager:
    """Manages persistent checkpoints and state recovery across workflow interruptions."""

    ALL_STEPS: tuple[str, ...] = (
        "ingest_and_transcribe",
        "observation_inventory",
        "story_mapping",
        "shot_planning",
        "composition_and_timing",
        "render_critic",
        "visual_repair",
        "package_delivery",
    )

    def __init__(self, work_dir: Path, run_id: str) -> None:
        self.work_dir = work_dir
        self.run_id = run_id
        self.checkpoint_path = work_dir / f"checkpoints_{run_id}.json"
        self.retry_budget_path = work_dir / f"retry_budgets_{run_id}.json"
        self._checkpoints: dict[str, VisualWorkflowCheckpoint] = {}
        self._retry_budgets: dict[str, PersistentRetryBudget] = {}
        self._load_checkpoints()
        self._load_retry_budgets()

    def _load_checkpoints(self) -> None:
        if self.checkpoint_path.exists():
            try:
                raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                for step_name, data in raw.items():
                    self._checkpoints[step_name] = VisualWorkflowCheckpoint.from_dict(data)
            except Exception:
                self._checkpoints = {}

    def _load_retry_budgets(self) -> None:
        if self.retry_budget_path.exists():
            try:
                raw = json.loads(self.retry_budget_path.read_text(encoding="utf-8"))
                for b_id, b_data in raw.items():
                    self._retry_budgets[b_id] = PersistentRetryBudget.from_dict(b_data)
            except Exception:
                self._retry_budgets = {}

    def get_retry_budget(
        self, budget_id: str, default_max_retries: int = 3
    ) -> PersistentRetryBudget:
        if budget_id not in self._retry_budgets:
            self._retry_budgets[budget_id] = PersistentRetryBudget(
                budget_id=budget_id,
                max_retries=default_max_retries,
                used_retries=0,
                exhausted=False,
            )
            self._save_retry_budgets()
        return self._retry_budgets[budget_id]

    def consume_retry(self, budget_id: str, default_max_retries: int = 3) -> PersistentRetryBudget:
        budget = self.get_retry_budget(budget_id, default_max_retries=default_max_retries)
        updated = budget.record_attempt()
        self._retry_budgets[budget_id] = updated
        self._save_retry_budgets()
        return updated

    def _save_retry_budgets(self) -> None:
        serialized = {k: v.to_dict() for k, v in self._retry_budgets.items()}
        write_text_atomic(self.retry_budget_path, json.dumps(serialized, indent=2))

    def save_checkpoint(
        self,
        step_name: str,
        status: WorkflowStepStatus,
        state_payload: dict[str, Any],
        evidence_files: Sequence[Path] = (),
    ) -> None:
        """Persists a verified checkpoint for a workflow step."""
        hashes: dict[str, str] = {}
        for f in evidence_files:
            if f.exists() and f.is_file():
                hashes[f.name] = _sha256_file(f)

        checkpoint = VisualWorkflowCheckpoint(
            step_name=step_name,
            status=status,
            state_payload=state_payload,
            evidence_hashes=hashes,
            timestamp_iso="2026-09-06T12:00:00Z",
        )
        self._checkpoints[step_name] = checkpoint

        serialized = {k: v.to_dict() for k, v in self._checkpoints.items()}
        write_text_atomic(self.checkpoint_path, json.dumps(serialized, indent=2))

    def plan_resumption(self) -> WorkflowResumePlan:
        """Inspects verified checkpoints and evidence on disk to form a recovery plan."""
        completed: list[str] = []
        pending: list[str] = []
        requires_reconciliation = False
        reconciliation_msg: str | None = None

        for step in self.ALL_STEPS:
            cp = self._checkpoints.get(step)
            if cp is not None:
                if cp.status == WorkflowStepStatus.UNCERTAIN_EXTERNAL:
                    requires_reconciliation = True
                    reconciliation_msg = f"Step '{step}' halted with uncertain external billing"
                    pending.append(step)
                elif cp.status == WorkflowStepStatus.COMPLETED:
                    # Verify evidence hashes still match files on disk
                    evidence_intact = True
                    for fname, expected_hash in cp.evidence_hashes.items():
                        fpath = self.work_dir / fname
                        if not fpath.exists() or _sha256_file(fpath) != expected_hash:
                            evidence_intact = False
                            break
                    if evidence_intact:
                        completed.append(step)
                    else:
                        pending.append(step)
                else:
                    pending.append(step)
            else:
                pending.append(step)

        last_comp = completed[-1] if completed else None
        return WorkflowResumePlan(
            run_id=self.run_id,
            last_completed_step=last_comp,
            completed_steps=tuple(completed),
            pending_steps=tuple(pending),
            can_resume=not requires_reconciliation,
            requires_external_reconciliation=requires_reconciliation,
            reconciliation_message=reconciliation_msg,
        )
