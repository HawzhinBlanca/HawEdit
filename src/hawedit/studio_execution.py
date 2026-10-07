"""Reconstruct persisted studio inputs; this record is not execution authority.

The protected worker must separately verify current runtime/model/owner/governance
authority, guard billing and checkpoints, and authenticate publication. HTTP stays
disabled until those boundaries are adopted. No models or providers run here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hawedit.studio_generation import (
    _BOOL_OPTIONS,
    _STRING_OPTIONS,
    GenerationError,
    GenerationRequest,
    ProducerSelection,
    _parse,
    prepare_generation,
)
from hawedit.studio_private import PrivateDirectory
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore

__all__ = ["PreparedStudioExecution", "prepare_studio_execution"]


@dataclass(frozen=True, slots=True)
class PreparedStudioExecution:
    """Validated inputs only; deliberately contains no client token or approval."""

    job_id: str
    source_id: str
    source_sha256: str
    request_sha256: str
    configuration_json: str
    argv: tuple[str, ...]


def prepare_studio_execution(
    job_id: str,
    store: SubmissionStore,
    uploads: UploadStore,
    *,
    producers: ProducerSelection,
    execution_binding_sha256: str,
    workflow_name: str,
) -> PreparedStudioExecution:
    """Reopen private persisted state and refuse capability/configuration drift.

    Expected binding and producer selection are host inputs, not proof of their
    authority. The returned argv must not bypass the protected worker's controls.
    """
    job = store.get(job_id)
    if (
        not isinstance(execution_binding_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", execution_binding_sha256) is None
        or job.execution_binding_sha256 != execution_binding_sha256
        or job.workflow_name != workflow_name
    ):
        raise GenerationError("Stored job differs from the host execution binding or workflow")

    args = _parse(job.arguments)
    # Decode values with the shared parser; inspect presence only. Exact rebuilding
    # below refuses duplicate flags, foreign capabilities and malformed option groups.
    present = {argument.partition("=")[0] for argument in job.arguments[1:]}
    options: dict[str, object] = {"preset": args.preset, "max_clips": args.max_clips}
    for key in _STRING_OPTIONS - {"preset"}:
        if "--" + key.replace("_", "-") in present:
            options[key] = getattr(args, key)
    for key in _BOOL_OPTIONS - {"silence_tightening"}:
        flag = key.replace("_", "-")
        if {"--" + flag, "--no-" + flag} & present:
            options[key] = getattr(args, key)
    if present & {
        "--silence-threshold-ms",
        "--silence-target-gap-ms",
        "--excise-fillers",
        "--no-excise-fillers",
    }:
        options["silence_tightening"] = args.silence_threshold_ms == 250

    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": job.source_id,
            # Content identity excludes this temporary validation-only token. It
            # is never reserved, returned or used as a client/replay capability.
            "client_token": "validation-only-token",
            "options": options,
        }
    )
    proposed_work = store.path.parent / "studio-artifacts" / job.job_id
    prepared = prepare_generation(request, uploads, proposed_work, producers)
    immutable_argv = tuple(arg for arg in prepared.argv if not arg.startswith("--work-dir="))
    if (
        immutable_argv != job.arguments
        or prepared.source_sha256 != job.source_sha256
        or prepared.content_sha256 != job.request_sha256
        or prepared.configuration_json != job.configuration_json
    ):
        raise GenerationError(
            "Stored job arguments, source or configuration do not match reconstruction"
        )

    # No work directory is created until every semantic check has succeeded.
    work = store.work_dir(job.job_id)
    PrivateDirectory(work, create=False).verify()
    store.get(job.job_id)
    return PreparedStudioExecution(
        job.job_id,
        job.source_id,
        prepared.source_sha256,
        prepared.content_sha256,
        prepared.configuration_json,
        prepared.argv,
    )
