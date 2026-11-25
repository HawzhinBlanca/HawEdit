# SD-B: Authenticated Publication Consumption

Date: 2026-10-03. Approved scope: signed-delivery-plan.md, SD-B. Parent implementation
baseline: 9bec30986dded0a77b3d1299c20b29a03de1520d. One writer; local commits only.
This is engineering research and diagnostic evidence, not gate/CI acceptance or reel quality.

## Grounding And Callers

BLUEPRINT sections 2-5, D-263's measured delivery, D-274's episode states and D-277's
authenticated review extension govern this unit. Actual Serena LSP definition/reference
records are retained in SD-B-before-map.json (18 records), before-contrast-map.json,
before-private-map.json, caller-test-map.json, review-test-helper-map.json,
completion-control-map.json and type-portability-map.json. These are not guessed signatures.
The signed-delivery-impact-map.md records affected production and diagnostic callers.

Plain QcRecord and Qc.human_reviewed previously reached direct publication or promotion.
The old 30-byte promotion positive demonstrated that structurally plausible measurement
JSON and hashes do not establish decoded media. Neither a verified receipt nor a cached
measurement is sufficient authority. The replacement reopens raw signed artifacts, trusted
reviewer policy, original source, current producer and recorded media tools at consumption.

Single-clip and episode generation now produce owner-private review bundles regardless
of unsigned QC claims. Only the authenticated promotion path creates proof-bearing
publication. Diagnostic seven-file bundling remains possible; it is not publication authority.

## Observed Corrections

Actual signed synthetic white-on-black media exposed a stored contrast ratio of 0.05:
whole-band gray percentiles missed sparse glyphs and used nonlinear color units. New
real-pixel regressions failed before replacing that observation with detected stroke versus
immediate surround, using the existing linear-luminance contrast functions. The production
4.5 threshold is unchanged. Existing textured-background/no-ink regressions remain.

Actual fixture source clocks were video 4120 ms and audio 4162 ms. Video-only source
bounds wrongly refused an existing valid completion control. Use both observed clocks,
refusing disagreement beyond the existing D-263 1.5-frame tolerance. This does not grant
arbitrary timing drift. Both actual signed/decoded completion controls subsequently passed.

Fresh bundle roots and exclusive staging leaves must be owner-private before rendering.
POSIX mode changes apply only to descriptor-bound new members in the exclusive staging
leaf, never existing source/candidate/trust files. Unsafe existing roots refuse without repair.
Windows typing exposed unavailable POSIX os members; guarded dynamic resolution preserves
the same runtime ownership refusal and descriptor-bound permissions.

## Tests And Limits

Preserve every original failure log. SD-B-callers-third.log exercised eight entire related
test modules and finished with one failure: our episode test constructed human_reviewed
without the metadata already required by Qc. The corrected test supplies explicitly unsigned
test claims and still requires both items PENDING_REVIEW, private directories, all media,
sidecars, plan and poster. No test was disabled or golden/fixture changed.

Existing true completeness controls now publish actual signed, decoded and reconciled test
media before checking completeness and each mutation. Negative publication cases first
publish the intact signed packet in an independent namespace. Damages include all nine
members, signed invalid media with plausible cached measurements, stale cache, changed
source/configuration/revision/producer/trust and partial signed watch claims. Ephemeral test
keys are not production trust. Synthetic mechanics are not native-editor acceptance.

SD-B-fast-third.log records lint and strict typing green on 303 files; it is explicitly not
the full gate. Final focused XML/log and then exact clean-commit canonical verification are
required. No ledger row is accepted without canonical green and required same-SHA CI.
Prior 9bec clean gate failed VEX source-package binding (#24); do not re-sign or alter that
evidence without the authorized review. Independent corpus/editor studies, actual model
access, AA/NVDA/browser journey, performance, CI and 30-day acceptance remain outstanding.

Recorded native mechanics host: HawaPC01, Windows 11 10.0.26200, CPython 3.12.10,
pytest 9.1.1, ruff 0.9.6, mypy 1.15.0, DBOS 2.29.0, OpenSSH_for_Windows 9.5p2,
Gyan FFmpeg 8.1.1 (not the project-pinned release toolchain). No paid provider calls.

## Next Boundary

Current web.py do_POST(/api/repurpose) and readiness route still return
studio_runner_unavailable. SubmissionStore, serial DBOS dispatch and guarded billing
components exist but do not themselves constitute a connected protected producer worker.
SD-C must connect the actual worker and job/revision/export identity; no complete creator
workflow is claimed. SD-C-before-map.json is a fresh actual caller map for that subsequent
unit, not evidence that it is implemented.
