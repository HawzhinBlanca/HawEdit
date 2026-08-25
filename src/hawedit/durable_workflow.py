"""§3's runner, wrapped so it survives the process dying partway through it.

`run_pipeline` already reports every stage as it happens (`events.py`, D-A1). What it still
cannot do is come back: kill the Windows process during a real multi-hour run and the next
invocation starts from argv again, paying for whatever GPU work happened to not be
digest-cached. `AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` Phase 1 calls for exactly one
more thing on top of the event stream — "wrap the current CLI/pipeline invocation as a coarse
DBOS workflow and durable step" — and this module is that wrapper, nothing more.

**Coarse, deliberately.** One `@DBOS.step()` around the entire `_build_and_run` call, not one
step per §3 stage. The architecture record is explicit about why a coarse step is *correct*
here rather than merely simple: "a recovered DBOS workflow can safely re-enter a coarse HawEdit
stage and let the pipeline's existing digest checks reuse completed work" — `TranscriptStore`
already refuses to re-transcribe a digest it has seen, visual embeddings are already cached per
window, delivery already resumes over an abandoned attempt (`resumed_over`, D-146). Splitting
into per-stage DBOS steps would duplicate resumability the pipeline already has and is Phase
5's job, triggered only if HawEdit becomes a genuinely distributed service — see that document.

**What "durable" buys, verified rather than assumed.** Two properties, checked against the
installed `dbos==2.29.0` source before being relied on — its Python API is not fully documented
publicly at the time of writing, and guessing decorator signatures for a system whose entire
job is correctness under a crash would be exactly the wrong place to guess:

1. *Crash/restart.* `DBOS.launch()` calls `startup_recovery_thread` for every workflow this
   executor left `PENDING`, unconditionally (`dbos/_dbos.py::_launch`, "Recover local workflows
   if not using a recovery service") — a process that starts back up and calls `configure_dbos`
   resumes work it did not finish, with no code in this module deciding to. `tests/
   test_durable.py::test_a_process_killed_mid_step_resumes_in_the_next_process` proves this
   against a real second OS process, not a same-process reconstruction.
2. *Duplicate submission.* A `start_workflow`/direct call under `SetWorkflowID(same_id)`, made
   after the first has completed, returns the recorded result rather than re-invoking the
   function (`dbos/_core.py`, "Directly return the result if the workflow is already
   completed") — measured directly, not read off a docstring: calling the workflow twice under
   one ID executes the step body exactly once.

**Small references across the DBOS boundary, per the same document's constraint.** The
workflow's argument is `argv: list[str]` — the same shape `hawedit.pipeline.main` already
accepts — and its return is `run.to_dict()`, the same JSON-safe document `--json` already
produces and `tests/test_pipeline.py::test_the_run_report_serializes_to_json` already pins.
Neither is new surface to trust: no transcript text, no frame bytes, no live producer object
(a `GeminiJudge` holds an API key in memory — pickling it into DBOS's checkpoint store would
write that key into `.dbos/hawedit.sqlite`) crosses the boundary. The step reconstructs every
producer from `argv` exactly as `_build_and_run` always has.

**The Run Event Ledger, minimally.** `events.py`'s `on_event` sink is wired here to an
append-only JSONL file beside the run's other artifacts (`work_dir / "events.jsonl"`), flushed
per line, and the step's own return value is mirrored to `work_dir / "report.json"` — the same
document, on disk, atomically written. Both exist for the same reason: DBOS checkpoints the
step's result in its own opaque system database, which answers "what did the workflow return"
to a caller holding the workflow ID, not "what is on disk for this run" to `agent.py`'s tools
(Phase 2), which are a separate process with only the work directory to read.
`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` describes a Postgres Artifact Ledger as the
agent's eventual world model — that is real scope, and it is not this file's: nothing reads
these back except `read_events`/`agent.py`'s tools, there is no derivation graph, and Postgres
buys nothing Phase 1 or 2 needs when the only reader is a human or one read-only agent replaying
a single run's own history. ponytail: two flat files are the whole ledger for now; move to the
Postgres schema in that document's "Artifact
Ledger" section when a second reader (a UI, a second process) actually needs to query across
runs rather than replay one.

**SQLite, not Postgres, and that is also the document's own call, not a shortcut around it.**
DBOS's own system database — where it checkpoints workflow/step state, the mechanism the two
properties above depend on — defaults to a local SQLite file when `system_database_url` is
unset (verified: `dbos/_dbos_config.py`, `f"sqlite:///{name}.sqlite"`). The architecture record
scopes Postgres to when HawEdit becomes distributed or multi-host; neither is true of a single
Windows box running one CLI at a time, so `configure_dbos` uses SQLite by default and accepts an
override for the day that changes.

**Why this is its own module, separate from `durable.py`.** `dbos` lives in the `agentic` extra,
not a base dependency — matching `torch`, `transformers`, `omnilingual_asr`, every other heavy
optional import in this codebase, all of which are deferred behind a function-local `try:
import ... except ImportError`. `@DBOS.workflow()`/`@DBOS.step()` cannot be deferred that way:
they decorate module-level functions, so `from dbos import DBOS` has to run at import time for
this module to exist at all. `durable.py`'s `main()` imports this module only *after* handling
`--help` — measured on a clean wheel install with no extras: `hawedit-durable --help` raised
`ModuleNotFoundError: No module named 'dbos'` before this split, because `--help` is supposed to
be a pure no-op and importing this module is not one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dbos import DBOS, SetWorkflowID

from hawedit.atomic_fs import write_text_atomic
from hawedit.events import JsonlEventSink, read_events
from hawedit.pipeline import _build_and_run, build_parser

__all__ = [
    "configure_dbos",
    # Re-exported: `read_events` moved to `events.py` (D-A8, the ledger format's own home), and
    # every existing caller imported it from here. Kept so that move is not a breaking change
    # for them, rather than making the format's relocation their problem.
    "read_events",
    "run_durable",
    "run_pipeline_workflow",
]

_DEFAULT_SYSTEM_DB = Path(".dbos") / "hawedit.sqlite"


def configure_dbos(system_database_url: str | None = None) -> None:
    """Construct and launch the process-wide DBOS instance.

    Safe to call more than once: both `DBOS(config=...)` and `DBOS.launch()` guard against
    double-init internally (`dbos/_dbos.py`: `__init__` returns immediately once
    `self._initialized`, `_launch` returns with a warning once `self._launched`) — checked
    against the installed source rather than assumed, since a silent *second* real init would
    mean a second recovery pass racing the first. This function therefore carries no flag of
    its own; DBOS's is authoritative.

    Args:
        system_database_url: where DBOS checkpoints workflow/step state. Omit for the default
            of `.dbos/hawedit.sqlite` under the current working directory — deliberately not
            the library's own bare default of `{name}.sqlite`, which would land wherever the
            process happened to be launched from. Tests pass an explicit `tmp_path` URL so a
            fixture never touches this default file.
    """
    url = system_database_url or f"sqlite:///{_DEFAULT_SYSTEM_DB}"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        Path(url[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)
    DBOS(config={"name": "hawedit", "system_database_url": url})
    DBOS.launch()


@DBOS.step()
def _run_pipeline_step(argv: list[str]) -> dict[str, Any]:
    """The one durable step: parse `argv`, build every producer it names, run, report.

    Everything inside is exactly what `hawedit.pipeline.main` already does for the same argv —
    `_build_and_run` is the shared function, not a reimplementation — plus a JSONL sink DBOS
    itself never sees or checkpoints; the step's checkpointed *result* is the returned dict,
    not the events along the way.
    """
    args = build_parser().parse_args(argv)
    sink = JsonlEventSink(args.work_dir / "events.jsonl")
    try:
        run = _build_and_run(args, on_event=sink)
    finally:
        sink.close()
    payload = run.to_dict()
    # `report.json`, beside `events.jsonl`: DBOS checkpoints this dict in its own opaque system
    # database, which answers "what did the workflow return" but not "what is on disk for this
    # run" — and the agent framework (`agent.py`, Phase 2) is a separate process that has only
    # the work directory to read. Written through `atomic_fs.write_text_atomic`'s staging-file-
    # and-rename, so a process killed mid-write leaves no half-written report for a reader to
    # trust. (That helper lived in `pipeline.py` as `_write_atomic` until the merge that brought
    # directory-shaped `artifact_bundle.py` publication in — D-A26.)
    write_text_atomic(
        args.work_dir / "report.json", json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return payload


@DBOS.workflow()
def run_pipeline_workflow(argv: list[str]) -> dict[str, Any]:
    """The coarse Phase 1 workflow: one step, wrapping one call to `_build_and_run`."""
    return _run_pipeline_step(argv)


def run_durable(argv: list[str], run_id: str | None = None) -> dict[str, Any]:
    """Run `argv` through the durable workflow. Configures and launches DBOS if not already.

    Args:
        run_id: the DBOS workflow ID. Omit for a fresh UUID every call — the ordinary case, and
            what a fresh submission should get. Supply one when the caller already has an
            idempotency key of its own (a queued job's ID, a request that might be retried by
            its transport) and a second submission under the same key must return the first
            run's result rather than pay for the work twice.

    Raises:
        Exactly what `_build_and_run` raises for a bad `argv` — this call is synchronous, so a
        malformed combination of flags fails here, before DBOS records anything durable to
        recover.
    """
    configure_dbos()
    if run_id is None:
        return run_pipeline_workflow(argv)
    with SetWorkflowID(run_id):
        return run_pipeline_workflow(argv)
