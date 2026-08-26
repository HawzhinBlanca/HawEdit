# Plan — pyannote diarization adapter (§3 Stage 0)

## Approach

The seam is finished; only the model boundary is missing. `attach_diarization`
(`ingest.py:688`) already sorts, type-checks, `assert_exclusive`s and range-checks whatever a
producer returns, and `run_pipeline` already accepts `diarizer=`. So the whole change is:

1. one class implementing `diarize(audio: Path) -> Sequence[Segment]`,
2. one CLI flag that constructs it,
3. an ADR for the dependency.

**New module `src/hawedit/pyannote_adapter.py`.** Not `diarization.py` — that module is pure
analytics (`diarization_error_rate`, DER components) imported by `diarization_acceptance.py`,
and putting a torch import in its path would make the acceptance kit unrunnable without a GPU
stack. `pyannote.audio` is imported *inside* `diarize`, the way `OpenCvFaceTracker.track`
imports `cv2` (`reframe.py:182`), so `import hawedit.pyannote_adapter` stays free.

**Conversion is the only real design decision.** pyannote yields float seconds; `Segment`
demands exact ints. `round()` is monotonic, and `assert_exclusive` compares `later.start_ms <
earlier.end_ms` strictly, so rounding **cannot** manufacture an overlap from non-overlapping
floats and touching boundaries stay legal. Therefore: round, never repair. A genuine model
overlap is refused by `attach_diarization`, which is D-243's intent, not a bug to work around.

**A turn that rounds to zero length is refused, not dropped** (AC-6). Dropping it would be the
silent-evidence-loss this repo exists to prevent, and no tolerance can be justified yet because
nobody here has seen this model's output — inventing one now would be recording a number rather
than a fact (D-073's phrasing, and the reason it was originally right even though its pinning
conclusion was later reversed). If real output shows this fires on harmless artifacts, that is
evidence for a follow-up ADR.

**Revision agreement (AC-4).** `diarization_acceptance.COMMUNITY_REVISION` is
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` and `models/revisions.json` carries the same value.
The adapter imports the constant rather than restating it, so the acceptance kit and the runtime
cannot drift apart.

## Explicitly out of scope

- **Speaker/face association** (`SpeakerSubjectTracker`, `Reframe.SPEAKER_TRACKED`). D-241 made
  it a separate seam on purpose. It needs a real association algorithm and, to be judged at all,
  diarization output somebody has actually looked at. Its own plan, after this lands.
- **Any accuracy claim.** No DER, no boundary error, no association error (AC-10).
- **§8.1 benchmarking against 3.1.** `diarization_acceptance.py` already covers that path and is
  human-signed; nothing here touches it.

## Files and symbols

| file | change |
|---|---|
| `src/hawedit/pyannote_adapter.py` | **new** — `PyannoteDiarizer`, `create_diarizer` |
| `src/hawedit/pipeline.py` | `build_parser` +`--diarize`/`--diarize-device`; `_build_and_run` constructs and passes `diarizer=` |
| `pyproject.toml` | new `diarization` optional extra |
| `DECISIONS.md` | new ADR — dependency + licence audit + conversion rule |
| `tests/test_pyannote_adapter.py` | **new** |
| `tests/test_pipeline.py` | CLI flag + wiring tests |

## Dependency (ADR owed)

- **`pyannote.audio`** — MIT. Not NonCommercial. ✅
- Pulls `torch` (BSD-3-Clause), already pinned in the `media` extra at `2.13.0`.
- Model `pyannote/speaker-diarization-community-1` — **CC-BY-4.0**, attribution required, not
  NonCommercial ✅. Attribution is already automatic via `registry.attribution_notices()`
  (`registry.py:570`); nothing to add.
- **Exact version is not pinned in this plan on purpose.** It must be the version that actually
  resolves against the pinned `torch==2.13.0`, recorded from the resolved wheel in the ADR. A
  version guessed here would be exactly the "number rather than a fact" this repo rejects.
  §3 Stage 0 says "pyannote.audio **4.x**" (`BLUEPRINT.md:108`), which bounds it.

## Divergence from BLUEPRINT

None. This implements §3 Stage 0's named model and §7's table row.

## Risks

- **BLOCKED.md #4 is live and this does not clear it.** `HF_TOKEN` is unset and the weights are
  not downloaded. Every task below is verifiable *without* the model — the adapter's contract,
  conversion and refusals are testable against a stub — but **nothing is verifiable against real
  model output** until Hawa accepts the licence. T6 is deliberately unstartable until then, and
  the feature is not "done" without it.
- `build_parser` now has three callers (`main`, `durable.py:47`, `durable_workflow.py:137`).
  A new flag with a default reaches all three; the impact map lists their tests.
- `PipelineRun.complete` becoming *reachable* changes exit codes for the first time. Any test
  asserting "always incomplete" would be pinning a defect — none found, but T5 checks.

## Open question for the owner

AC-6 refuses a sub-millisecond turn outright. The alternative is dropping it and reporting the
count. I chose refusal because it cannot hide anything, but it can fail a whole run on a model
artifact. Say the word if you would rather it drop-and-report.

Approved-by: Hawa (in chat, 2026-08-26) — approved as written, T1 to start.
