# Tasks ledger — diarization-adapter
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  ADR: pyannote.audio dependency, licence audit (MIT code / CC-BY-4.0 model, neither
          NonCommercial per D-002), the round-never-repair conversion rule, and the AC-6
          refusal. Adds the `diarization` extra to pyproject with the version that actually
          resolves against the pinned torch==2.13.0 — recorded from the resolved wheel, not
          guessed.                                        (tests: test_the_diarization_extra_pins_a_four_x_pyannote)

- [ ] T2  `PyannoteDiarizer.diarize` conversion + refusals, against a stubbed pyannote
          `Annotation`. No model, no network.              (tests: test_float_seconds_become_exact_integer_milliseconds,
                                                                  test_a_turn_that_rounds_to_zero_length_is_refused_not_dropped,
                                                                  test_the_adapter_never_repairs_an_overlap_it_is_handed)

- [ ] T3  Checkpoint resolution: `ModelStore.assert_available`, the `BLOCKED.md` #4 message, and
          the revision agreement with `diarization_acceptance.COMMUNITY_REVISION`.
                                                           (tests: test_absent_weights_are_refused_by_naming_blocker_four,
                                                                  test_a_checkpoint_revision_the_acceptance_kit_did_not_pin_is_refused)

- [ ] T4  Missing `pyannote.audio` surfaces as `DiarizationUnavailable` naming the extra, and the
          run continues to a structured Stage 0 skip rather than crashing (D-240).
                                                           (tests: test_missing_pyannote_is_reported_as_a_missing_extra,
                                                                  test_an_unavailable_diarizer_leaves_the_rest_of_stage_0_intact)

- [ ] T5  `--diarize` / `--diarize-device` on `build_parser`; `_build_and_run` constructs and
          passes `diarizer=`. Default-off must stay invisible to all six existing callers.
                                                           (tests: test_the_default_run_does_not_enable_diarization,
                                                                  test_the_diarize_flag_reaches_run_pipeline_as_a_producer,
                                                                  test_run_durable_reports_the_same_thing_a_direct_call_would)

- [ ] T6  **BLOCKED on BLOCKED.md #4.** First real run against the gated checkpoint: confirm the
          output is exclusive under `assert_exclusive`, that no turn rounds to zero, and that
          `PipelineRun.complete` becomes reachable. Record it in `evidence/` with the hardware
          and library versions. Cannot be started until `HF_TOKEN` exists and the licence is
          accepted.                                        (tests: test_a_measured_diarization_run_can_report_complete)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] AC-10 respected: no DER / boundary / association number claimed anywhere

## Note on T6
T1–T5 are fully verifiable without the model and deliver a real capability: the CLI can enable
diarization and every refusal path is proven. They do **not** make the feature done. Until T6
runs, `BLOCKED.md` #4 stays open and M3.3/M8.1 stay PARTIAL exactly as D-241 requires.
