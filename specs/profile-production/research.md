# Research — `--profile production` Enforcement (Task T1.9)

## 1. Context & Background
HawEdit's philosophy is "Strict Fail-Stop / Zero Silent Fallbacks" (GEMINI.md) and "Nothing Skipped Quietly" (pro-grade program §0).
Task T1.9 introduces the `--profile production` execution mode:
> "A run in this profile refuses to deliver if any of: diarization skipped, Path A skipped, Stage 4 judged without frames, Path B skipped (once T4.2 lands), reconciliation not run, no review record, any stage `StageSkipped`. Default profile unchanged; the contract carries `profile`."

Task T1.6 already added `profile: str = "production"` to the `Provenance` dataclass in `src/hawedit/clip.py` and bound it to `Clip.provenance`.
Now we need to wire `--profile` through the CLI, pipeline runner, and delivery gate.

## 2. Real Code Surface Mapping
- **CLI Parser**: `build_parser()` in `src/hawedit/pipeline.py` (line 2724). Needs `--profile` argument accepting choices `("default", "production")`, defaulting to `"default"`.
- **Runner Entrypoints**:
  - `_build_and_run(args, ...)` in `src/hawedit/pipeline.py` (line 2930) passes `profile=args.profile`.
  - `run_pipeline(...)` in `src/hawedit/pipeline.py` (line 1544) accepts `profile: str = "default"`.
  - `clip = Clip(..., provenance=Provenance.current(profile=profile))` (line 2360) records the active profile in the contract.
- **Delivery Enforcement**:
  - In `run_pipeline` delivery publication block (lines 2520–2555):
    Under `profile == "production"`:
    1. Check `run.skipped()`: if any stage was skipped (e.g. diarization, transcript, visual index, discovery, editorial, render), delivery is refused with `DeliveryRefused("production_profile_skipped_stage")`.
    2. Check human review: `qc` must be present, `qc.human_reviewed` must be `True`, and `qc.reviewed_sha256` must match the delivered file. If missing, refuse delivery with `DeliveryRefused("production_profile_unreviewed")`.
  - In `src/hawedit/delivery.py`:
    `reconcile_delivery` can also check `clip.provenance.profile`: if `profile == "production"`, enforce that human review binding is non-null and matches.

## 3. Existing Guarantees & Constraints
- The default profile remains `"default"`. Existing runs and tests that do not specify `--profile` must continue to function without disruption.
- `PipelineRun.skipped()` already dynamically introspects all fields of the run for `StageSkipped`.
- When delivery is refused, `run_pipeline` catches `DeliveryRefused` and marks `delivery` as `StageSkipped(stage="delivery", blocked_by=("production profile",))` without publishing any bundles.
