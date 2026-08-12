"""Phase 5 — "scale only when triggered": a checked answer, not a silent guess, plus a real
migration path grounded in what this codebase actually looks like today.

`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` names five explicit conditions for moving off
DBOS to Temporal (lines 124-130 — quoted verbatim in `SCALE_TRIGGERS` below). Per the user's own
choice for this branch — a trigger check and a migration path, not the distributed stack itself
— this module is deliberately not a Temporal integration, a worker-service scaffold, or an
OpenLineage exporter. Building any of those now, with no evidence any trigger has fired, would
be the exact infrastructure-before-the-trigger mistake D-A11 declined for a Postgres role and
D-A14 declined for a generic version registry.

**None of the five conditions are measurable from this codebase's own state.** They are
organizational and deployment facts — multi-tenancy, physical worker-pool topology, contractual
retention requirements — that no static analysis of a single-process CLI can observe.
`evaluate_scale_triggers` therefore takes an explicit, named answer for every condition rather
than defaulting any of them to "no": silently assuming none apply would be exactly the
unverified claim `reason_code`'s own "required, never assumed" rule (D-A13) exists to prevent,
applied to a bigger decision. An assessment with a missing answer raises rather than treating
silence as "not triggered."

**The migration path is a function, not a `.md` file, so it cannot drift unnoticed.** A static
document describing "what would need to change" goes stale the moment the code it describes
does, and nothing would catch it — this repository's own `test_claims.py` exists precisely
because that already happened to other documents here. `describe_migration_path()` returns
prose that names real modules and functions, and `tests/test_scale.py` asserts each one still
exists — the same discipline `test_the_module_map_covers_every_module` already holds the
README's own module table to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "SCALE_TRIGGERS",
    "ScaleAssessment",
    "ScaleTrigger",
    "describe_migration_path",
    "evaluate_scale_triggers",
]


@dataclass(frozen=True, slots=True)
class ScaleTrigger:
    """One of the record's own five conditions, quoted rather than paraphrased."""

    number: int
    condition: str


# Verbatim from AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md, "Move from DBOS to Temporal ...
# when one or more of these are true" (lines 124-130). Numbered as the record numbers them, so
# an assessment can cite "#3" and mean the same thing the document does.
SCALE_TRIGGERS: Final[tuple[ScaleTrigger, ...]] = (
    ScaleTrigger(
        1, "HawEdit schedules work across multiple independently deployed physical worker pools."
    ),
    ScaleTrigger(
        2,
        "It becomes a multi-tenant hosted service with strict high-availability and isolation "
        "requirements.",
    ),
    ScaleTrigger(
        3,
        "Cross-region recovery, long retention and mature workflow-operations tooling become "
        "contractual requirements.",
    ),
    ScaleTrigger(
        4,
        "Workflow history and worker deployment lifecycles can no longer be managed safely by "
        "the application and its PostgreSQL deployment.",
    ),
    ScaleTrigger(
        5,
        "The team needs Temporal's operational ecosystem enough to justify the additional "
        "service and worker infrastructure.",
    ),
)


@dataclass(frozen=True, slots=True)
class ScaleAssessment:
    """The outcome of checking every trigger, and who checked it."""

    triggered: tuple[ScaleTrigger, ...]
    recommend_migration: bool
    assessed_by: str

    def __post_init__(self) -> None:
        if not self.assessed_by.strip():
            raise ValueError(
                "an assessment needs a named assessor; an unattributed one is not one."
            )
        if self.recommend_migration != bool(self.triggered):
            raise ValueError(
                "recommend_migration must agree with whether any trigger fired — "
                f"got recommend_migration={self.recommend_migration} with "
                f"{len(self.triggered)} triggered."
            )


def evaluate_scale_triggers(answers: dict[int, bool], assessed_by: str) -> ScaleAssessment:
    """Check every one of the record's five conditions against an explicit answer for each.

    Args:
        answers: `{trigger number: is this true today}` — must cover every number in
            `SCALE_TRIGGERS` and no others. A missing answer is refused rather than treated as
            "no": the whole point is that nobody may assume a condition does not apply.
        assessed_by: who is making this assessment. Required and non-blank.

    Raises:
        ValueError: `answers` is missing a trigger, names one that does not exist, or
            `assessed_by` is blank.
    """
    declared = {trigger.number for trigger in SCALE_TRIGGERS}
    given = set(answers)
    missing = declared - given
    if missing:
        raise ValueError(
            f"no answer given for trigger(s) {sorted(missing)} — every condition must be "
            f"explicitly assessed, never assumed false."
        )
    unknown = given - declared
    if unknown:
        raise ValueError(f"answers given for trigger(s) that do not exist: {sorted(unknown)}")

    triggered = tuple(trigger for trigger in SCALE_TRIGGERS if answers[trigger.number])
    return ScaleAssessment(
        triggered=triggered, recommend_migration=bool(triggered), assessed_by=assessed_by
    )


def describe_migration_path() -> str:
    """What would actually have to change to move HawEdit's durable execution from DBOS to
    Temporal, grounded in this codebase's real module boundaries rather than generic advice.

    Every module and function named here is asserted to exist by `tests/test_scale.py`, so this
    cannot describe a migration through code that has since been renamed or removed.
    """
    return (
        "DBOS-specific code is already isolated to one module: `src/hawedit/durable_workflow.py` "
        "is the only place `@DBOS.step()`/`@DBOS.workflow()` appear, and `src/hawedit/durable.py` "
        "is the only caller that imports it — one function-local import of `run_durable()`, "
        "deferred past argument parsing so `--help` never needs `dbos` installed (D-A2/D-A3). "
        "Nothing in `agent.py`, `proposals.py`, `editor_agent.py`, `learning.py` or "
        "`promotion.py` imports `durable_workflow.py` at all — verified by grep, not assumed. A "
        "Temporal migration therefore rewrites that one module and its one call site, not every "
        "caller.\n\n"
        "What moves: `configure_dbos()`'s SQLite/Postgres system database becomes Temporal's own "
        "workflow history store; the single coarse `@DBOS.step()` around `_build_and_run()` "
        "becomes one or more Temporal Activities; `run_pipeline_workflow()`'s "
        "`@DBOS.workflow()` becomes a Temporal Workflow definition; cancellation semantics "
        "change — DBOS fails the *awaiter* rather than interrupting a running step (measured, "
        "M9.3), where Temporal's own cancellation API can signal the activity itself, a real "
        "behavioural difference worth re-verifying with the same kind of real-process-kill test "
        "`test_durable.py` already runs against DBOS, not assumed to carry over.\n\n"
        "What does not move: the Run Event Ledger (`events.py`'s `JsonlEventSink`/`read_events`), "
        "the decision-delta ledger (`learning.py`), and the judge promotion ledger "
        "(`promotion.py`) are all plain JSONL files with no DBOS dependency — a durable-execution "
        "engine swap changes how a run is *scheduled and recovered*, not the format of what it "
        "records about itself. `agent.py`'s tools read those files directly and would be "
        "unaffected.\n\n"
        "Not evaluated here, and explicitly out of scope until a trigger fires: OpenLineage "
        "export, dedicated worker-service deployment, and cross-region HA — the record's own "
        "Phase 5 language is 'evaluate ... against actual cross-host and interoperability needs', "
        "and there are none to evaluate against yet."
    )
