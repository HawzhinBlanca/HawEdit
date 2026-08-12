"""Append-only run events: what the pipeline is doing, while it is still doing it.

`PipelineRun` is the record of a finished run. It is complete, it is honest, and it arrives
too late for anything to watch. A 38-minute source spends most of an hour inside
`run_pipeline` with no way for a caller to learn that Stage 0 finished and Stage 3 started —
the function's only report is its return value. That is the one property the agentic upgrade
cannot work around: a durable workflow needs stage transitions to checkpoint, and an editor
watching a run needs them to see anything at all.

So this is the observer boundary, and deliberately nothing more:

**One additive parameter, and existing callers are unaffected.** `run_pipeline` takes an
`on_event` sink defaulting to `discard`. Every current caller — the CLI, the tests, `smoke.py`
— keeps working unchanged and pays one function call per stage for the privilege.

**A skip is not a completion.** `StageSkipped` exists because "did not run" and "ran and found
nothing" are different facts about the world; that distinction would be worthless if the event
stream flattened both to `completed`. `finished(stage, skipped=reason)` carries the reason the
stage record carries, and `RunEvent` refuses a skip with no reason and a completion with one.

**Sequence numbers, because a timestamp is not an order.** §Phase 1's replay contract is
"reconnect by workflow ID and last event ID, then replay the ledger". Two events inside the
same millisecond are ordinary — `at_ms` cannot be the cursor. The counter is per-log, starts
at 1, and never repeats.

**The sink is `Callable[[RunEvent], None]`, so `list.append` already is one.** A test collects
events with a plain list; a durable workflow passes a function that writes a row. Neither
needed a class here, so there is not one.

What this module deliberately does NOT do yet: no persistence, no run-level start/finish
event, no failure event. Those belong to the durable workflow that will call `run_pipeline`,
not to the pipeline being observed — see the `ponytail:` note on `RunEventLog`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "EventSink",
    "RunEvent",
    "RunEventLog",
    "RunState",
    "discard",
]


class RunState(Enum):
    """The three things that can be true of a stage while a run is in flight."""

    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One stage transition, as a value that can be written down and replayed.

    Validated at construction for the same reason `JudgeVerdict` is: this is the record a UI
    timeline and a workflow ledger both read, and a malformed one is discovered later and
    further away, when someone is trying to work out why a run appears to be running still.
    """

    run_id: str
    sequence: int
    at_ms: int
    stage: str
    state: RunState
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("a run event belongs to a run; run_id is empty")
        if not self.stage.strip():
            raise ValueError(f"run event {self.sequence} names no stage")
        if self.sequence < 1:
            raise ValueError(f"event sequence starts at 1, not {self.sequence}")
        if self.at_ms < 0:
            raise ValueError(f"event timestamp {self.at_ms} is before the epoch")
        # A skip whose reason is blank is the failure this module exists to prevent: it reads
        # as "this stage did not run" with nothing to act on, which is exactly the report
        # `StageSkipped` was built to stop `PipelineRun` from making.
        if self.state is RunState.SKIPPED and not self.reason.strip():
            raise ValueError(
                f"stage {self.stage!r} is reported skipped with no reason. A skip nobody can "
                f"explain is indistinguishable from a stage that was forgotten."
            )
        if self.state is not RunState.SKIPPED and self.reason:
            raise ValueError(
                f"stage {self.stage!r} is {self.state.value} and carries reason "
                f"{self.reason!r}. Only a skip has a reason; anything else here is a note "
                f"that would be read as a refusal."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "at_ms": self.at_ms,
            "stage": self.stage,
            "state": self.state.value,
            "reason": self.reason,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> RunEvent:
        """The inverse of `to_dict`, for a sink that persists events as JSON and reads them back.

        `durable.py`'s JSONL ledger is the first caller: one `to_dict()` per line out, one
        `from_dict()` per line back in, with `RunEvent.__post_init__` re-validating every field
        exactly as it did the first time — a line a crash left half-written fails to parse as
        JSON before it ever reaches here, rather than silently reconstructing a truncated event.
        """
        return RunEvent(
            run_id=str(data["run_id"]),
            sequence=int(data["sequence"]),
            at_ms=int(data["at_ms"]),
            stage=str(data["stage"]),
            state=RunState(str(data["state"])),
            reason=str(data.get("reason", "")),
        )


EventSink = Callable[[RunEvent], None]


def discard(event: RunEvent) -> None:
    """The default sink: a run nobody is watching costs one call per stage."""


class RunEventLog:
    """Stamps and emits stage transitions for one run.

    ponytail: no run-level `run.started`/`run.completed`/`run.failed` events here. For those,
    the run *is* the `run_pipeline` call — its start is the call and its end is the return or
    the exception, both of which the caller already has. The durable workflow that will wrap
    this call in Phase 2 is that caller, and it is also the only layer that can honestly report
    a crash, since a process that dies mid-stage emits nothing from inside itself. Adding them
    here would mean threading a terminal event through seven `return` statements to duplicate
    what a `try/finally` one level up expresses once.
    """

    def __init__(
        self,
        run_id: str,
        sink: EventSink = discard,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not run_id.strip():
            raise ValueError("a run event log belongs to a run; run_id is empty")
        self.run_id = run_id
        self._sink = sink
        self._clock = clock
        self._sequence = 0

    def started(self, stage: str) -> RunEvent:
        return self._emit(stage, RunState.STARTED)

    def finished(self, stage: str, skipped: str | None = None) -> RunEvent:
        """Report how `stage` ended.

        Args:
            skipped: the stage's own reason for not running, taken from the `StageSkipped` this
                run recorded. `None` means the stage ran. Passing the reason rather than the
                record keeps this module free of a pipeline import — and free of the cycle that
                import would create — while still refusing a reasonless skip.
        """
        if skipped is None:
            return self._emit(stage, RunState.COMPLETED)
        return self._emit(stage, RunState.SKIPPED, skipped)

    def _emit(self, stage: str, state: RunState, reason: str = "") -> RunEvent:
        self._sequence += 1
        event = RunEvent(
            run_id=self.run_id,
            sequence=self._sequence,
            at_ms=int(self._clock() * 1000),
            stage=stage,
            state=state,
            reason=reason,
        )
        self._sink(event)
        return event
