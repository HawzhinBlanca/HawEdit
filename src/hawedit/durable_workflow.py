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
per line. `AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` describes a Postgres Artifact Ledger as
the agent's eventual world model — that is real scope, and it is not this file's: nothing reads
this ledger back except `read_events`, there is no derivation graph, and Postgres buys nothing
Phase 1 needs when the only reader is a human replaying one run's own history. ponytail: a flat
JSONL file is the whole ledger for now; move to the Postgres schema in that document's "Artifact
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

from hawedit.events import RunEvent
from hawedit.pipeline import _build_and_run, build_parser

__all__ = [
    "configure_dbos",
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


class _JsonlEventSink:
    """Appends every `RunEvent` to one file, flushed immediately.

    Flushed per line, not buffered, because the property this exists for is that a crash mid-
    run leaves every event already emitted durably on disk — a buffered sink would lose exactly
    the events a crash-recovery reader most needs, the ones nearest the crash. `read_events` is
    the only reader, and it tolerates a torn last line: a real crash can land mid-`write`, and
    the line before it must still parse.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a", encoding="utf-8")

    def __call__(self, event: RunEvent) -> None:
        self._handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def read_events(path: Path) -> tuple[RunEvent, ...]:
    """Read one run's event ledger back, tolerating a line a crash left half-written.

    Raises:
        FileNotFoundError: no run wrote to `path`.
    """
    events: list[RunEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                events.append(RunEvent.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                # A torn last line — a crash landed between the `write` and the newline it
                # writes together with the payload. Every earlier line already parsed and is
                # kept; this one is the record of exactly how far the run got, which the
                # skip/complete stage records in `run.to_dict()` already say more reliably.
                break
    return tuple(events)


@DBOS.step()
def _run_pipeline_step(argv: list[str]) -> dict[str, Any]:
    """The one durable step: parse `argv`, build every producer it names, run, report.

    Everything inside is exactly what `hawedit.pipeline.main` already does for the same argv —
    `_build_and_run` is the shared function, not a reimplementation — plus a JSONL sink DBOS
    itself never sees or checkpoints; the step's checkpointed *result* is the returned dict,
    not the events along the way.
    """
    args = build_parser().parse_args(argv)
    sink = _JsonlEventSink(args.work_dir / "events.jsonl")
    try:
        run = _build_and_run(args, on_event=sink)
    finally:
        sink.close()
    return run.to_dict()


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
