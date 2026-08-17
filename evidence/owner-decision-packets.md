# Evidence-bound owner decision packets

Date: 2026-08-17

Scope: autonomous preparation for HK-8. This artifact does not contain an owner decision and does
not close `BLOCKED.md` #9, #13, #14, #15, #18 or #21.

## Implemented boundary

`src/hawedit/decision_packets.py` reads the frozen `BLUEPRINT.md`, extracts the exact six blocker
sections and reopens every evidence file cited by the reviewed recommendations through stable,
no-follow, single-link reads. Expected SHA-256 identities are code-bound. Authority drift stops
publication and requires renewed research rather than carrying an old recommendation forward.

The published directory contains exactly six Markdown pages, `decisions.json`,
`owner-decisions.template.json` and `INSTRUCTIONS.txt`. The machine template repeats each allowed
option and reviewed recommendation but leaves `decided_by`, `decided_at_utc`, `rationale` and
`selected_option` unset. Pages state `OWNER DECISION: UNSET`; no fixture, default or green test is
approval. The output is deterministic and atomically published without replacing an existing
operator directory.

The operator command is:

```bash
python -m hawedit.decision_packets prepare --project-root . \
  --output-dir /secure/hawedit-owner-decisions
```

Successful stdout is one JSON document naming the packet, manifest and owner template. Authority
drift produces no success JSON and exits with a bounded `REFUSED` diagnostic.

## Automated evidence

On hawapc01, Windows, CPython 3.12.10, before the final commit:

- `tests/test_decision_packets.py`: **9 passed**, zero skips.
- Ruff check and format: clean for the new source and tests.
- mypy `--strict --no-incremental`: clean for `decision_packets.py`.
- Regressions cover all six unset choices, self-contained allowed/recommended identifiers,
  deterministic bytes, output overwrite, blueprint/blocker/evidence drift, hardlinked evidence,
  hidden serialized approval, machine-readable CLI success and refusal without false success.

The preceding pushed SHA `6903d43f926569b3f16b2d12bd1effc1930ec99f` passed the complete
local canonical gate with **2,629 passed / 0 skipped**. Its hosted Python 3.12 job exposed one
POSIX-only nested Vertex-frame cleanup defect after **2,628 passed**; that defect is corrected in the
current working tree and must pass a new exact-SHA hosted run before this unit is accepted.

## Human boundary

The packet cannot determine legal ownership, product scope or editorial risk tolerance. A
responsible owner must select exactly one listed identifier per blocker, supply rationale, identity
and UTC time, and then approve the corresponding ADR/blueprint/code consequences. Until that
happens, all six blockers remain open.
