"""Pinned DBOS dispatch for the studio's immutable submission outbox.

The caller must supply a registered protected worker, not an unguarded paid pipeline.
This mechanism is not model preflight, billing reconciliation or publication authority.
HTTP must remain refused until the protected producer worker is connected.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import version
from typing import Any

from dbos import DBOS, Queue, SetWorkflowID, WorkflowStatus

from hawedit.studio_generation import PreparedGeneration
from hawedit.studio_submissions import StoredSubmission, StudioStorageError, SubmissionStore

__all__ = [
    "STUDIO_QUEUE_NAME",
    "StudioQueueError",
    "configure_studio_queue",
    "reconcile_studio_submission",
    "submit_studio_workflow",
]

STUDIO_QUEUE_NAME = "hawedit-studio-v1"
StudioWorkflow = Callable[[str], dict[str, Any]]


class StudioQueueError(RuntimeError):
    """Dispatch is refused or uncertain; the same immutable identity must be reconciled."""


def configure_studio_queue() -> Queue:
    """Call after DBOS launch; refuse rather than overwrite conflicting persisted policy."""
    if version("dbos") != "2.29.0":
        raise StudioQueueError("The studio queue requires the reviewed DBOS 2.29.0 runtime")
    queue = DBOS.register_queue(
        STUDIO_QUEUE_NAME, concurrency=1, worker_concurrency=1, on_conflict="never_update"
    )
    if (
        queue.concurrency != 1
        or queue.worker_concurrency != 1
        or queue.priority_enabled
        or queue.partition_queue
        or queue.limiter is not None
        or queue.polling_interval_sec != 1.0
    ):
        raise StudioQueueError("Persisted studio queue configuration conflicts with serial policy")
    return queue


def _worker_name(workflow: StudioWorkflow) -> str:
    # Pinned 2.29.0 decorator metadata; no transitive/private DBOS import is needed.
    name = getattr(workflow, "dbos_function_name", None)
    if not isinstance(name, str) or not name:
        raise StudioQueueError("Studio dispatch requires a registered protected workflow")
    return name


def _validate_status(status: WorkflowStatus | None, job: StoredSubmission) -> None:
    if (
        status is None
        or status.workflow_id != job.job_id
        or status.name != job.workflow_name
        or status.queue_name != STUDIO_QUEUE_NAME
        or status.input is None
        or tuple(status.input["args"]) != (job.job_id,)
        or status.input["kwargs"] != {}
    ):
        raise StudioQueueError("DBOS dispatch evidence does not match the immutable studio job")


def reconcile_studio_submission(
    store: SubmissionStore, job_id: str, workflow: StudioWorkflow
) -> StoredSubmission:
    """Reconcile the two-database boundary without re-enqueueing recorded executions."""
    job = store.get(job_id)
    if _worker_name(workflow) != job.workflow_name:
        raise StudioQueueError("Registered workflow differs from the immutable submission")
    try:
        configure_studio_queue()
        status = DBOS.get_workflow_status(job.job_id)
        if status is None:
            with SetWorkflowID(job.job_id):
                handle = DBOS.enqueue_workflow(STUDIO_QUEUE_NAME, workflow, job.job_id)
            if handle.workflow_id != job.job_id:
                raise StudioQueueError("DBOS returned a different workflow identity")
            status = DBOS.get_workflow_status(job.job_id)
        _validate_status(status, job)
        store.confirm_dispatch(job.job_id)
        return store.get(job.job_id)
    except StudioStorageError:
        # Reserve was committed first. Even an acknowledgement-write failure retains its ID.
        raise
    except Exception as exc:
        message = (
            f"Queue acknowledgement uncertain ({type(exc).__name__}); "
            "reconcile this job with the same client token."
        )
        try:
            store.note_dispatch_error(job.job_id, message)
        except StudioStorageError:
            raise StudioQueueError(
                "Queue outcome and acknowledgement storage are unavailable"
            ) from exc
        raise StudioQueueError(message) from exc


def submit_studio_workflow(
    store: SubmissionStore,
    prepared: PreparedGeneration,
    execution_binding_sha256: str,
    workflow: StudioWorkflow,
) -> StoredSubmission:
    name = _worker_name(workflow)
    job = store.reserve(prepared, execution_binding_sha256, name)
    return reconcile_studio_submission(store, job.job_id, workflow)
