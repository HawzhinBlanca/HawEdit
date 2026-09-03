# Plan — `--profile production` Enforcement (Task T1.9)

## 1. Goal
Implement the `--profile production` execution mode in HawEdit CLI and pipeline runner, enforcing the "Nothing Skipped Quietly" canon at the delivery boundary:
- Refuse delivery if any stage is `StageSkipped`.
- Refuse delivery if human review record is absent.
- Ensure the output contract records the active profile in `Clip.provenance.profile`.
- Default profile remains `"default"` so non-production workflows and synthetic tests remain functional.

## 2. Changes
1. `src/hawedit/pipeline.py`:
   - Add `--profile` option in `build_parser()`, choices: `("default", "production")`, default: `"default"`.
   - Forward `profile=args.profile` in `_build_and_run()`.
   - Add `profile: str = "default"` to `run_pipeline()`.
   - Pass `profile=profile` into `Provenance.current(profile=profile)` during Stage 5 `Clip` construction.
   - At the delivery stage:
     ```python
     if profile == "production":
         skipped_stages = run.skipped()
         if skipped_stages:
             raise DeliveryRefused(
                 "production_profile_skipped_stage",
                 expected="zero skipped stages",
                 measured=f"skipped: {[s[0] for s in skipped_stages]}",
             )
         if qc is None or not qc.human_reviewed or not qc.reviewed_sha256:
             raise DeliveryRefused(
                 "production_profile_unreviewed",
                 expected="valid human review record with sha256 binding",
                 measured="unreviewed or missing qc record",
             )
     ```
2. `src/hawedit/delivery.py`:
   - In `reconcile_delivery()`:
     If `clip.provenance and clip.provenance.profile == "production"`:
       Ensure `clip.qc and clip.qc.human_reviewed and clip.qc.reviewed_sha256`.

3. Tests (`tests/test_delivery.py` & `tests/test_pipeline.py`):
   - `test_the_production_profile_cannot_deliver_with_a_skipped_stage`
   - `test_the_production_profile_requires_reconciliation_and_review_record`
   - `test_the_contract_records_the_profile_used`

Approved-by: Hawa
