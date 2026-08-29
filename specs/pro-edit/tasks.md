# Tasks ledger — pro-edit
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR: this extends §3 Stage 6, which specifies only "reframing, captions, encode".
          Records the owner's scope decision and the splicing risk.
                                  (tests: test_the_edit_extension_is_a_named_decision)

- [x] T2  The hook card: the judge's `title_ckb` is burned over the opening instead of discarded.
                                  (tests: test_the_hook_card_uses_the_judges_own_title,
                                          test_a_clip_without_a_title_renders_unchanged)

- [x] T3  Emphasis: the longest word of each caption event carries the accent, as a style change
          only — never a text change.
                                  (tests: test_the_longest_word_carries_the_emphasis,
                                          test_emphasis_never_alters_the_caption_text)

- [ ] T4  Silence tightening: internal pauses above the threshold are cut and every later caption
          shifts by the removed duration; the contract records the total.
                                  (tests: test_a_long_internal_pause_is_removed,
                                          test_captions_shift_with_the_removed_silence,
                                          test_the_removed_total_is_recorded)

- [x] T5  Punch-ins: the crop changes scale on sentence boundaries, so no clip is one framing
          throughout.
                                  (tests: test_the_crop_changes_scale_at_least_once,
                                          test_a_scale_change_lands_on_a_sentence_boundary,
                                          test_existing_single_framing_callers_are_unchanged)

- [ ] T6  Assembly: several moments become one reel, and the judge scores the assembly rather
          than the source spans.
                                  (tests: test_an_assembled_reel_is_judged_as_one,
                                          test_the_verdict_is_recorded_against_the_assembly,
                                          test_editorial_thresholds_apply_to_the_assembly)

- [x] T7  Speaker-tracked reframe, once `BLOCKED.md` diarization clears. Until then the reframe
          stays face-tracked and says so.
                                  (tests: test_an_unavailable_diarizer_never_claims_speaker_tracking)

- [x] T8  **Measure it on real footage.** Render ep29 before and after and record what changed in
          `evidence/`, including whether the judge's misleading-edit score moves on an assembly.
                                  (tests: test_the_measured_edit_evidence_is_recorded)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] T8's evidence states honestly whether the assembly scored worse than the single span
