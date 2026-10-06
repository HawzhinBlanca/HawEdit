# EARS Specification

1. WHEN correction alignment begins without a loaded draft model, THE backend
   SHALL load only the canonical CTC model/tokenizer through held verified assets.
   Tests: test_alignment_loads_only_held_ctc, test_alignment_verifies_before_import.
2. WHEN either CTC-only or dual-model construction fails at guard exit, THE backend
   SHALL leave no newly admitted cache. Test: test_ctc_guard_failure_does_not_admit_cache.
3. WHEN all canonical drafts succeed, THE native producer and worker SHALL release
   their real backend's draft model before validation, retaining CTC and identity.
   Tests: test_production_releases_draft_before_validation,
   test_release_retains_ctc_and_drops_draft.
4. WHEN a draft or release fails, THE production entry point SHALL halt without
   invoking validation or publishing a transcript.
   Tests: test_production_draft_failure_never_hands_off,
   test_production_release_failure_never_validates.
5. WHEN adapter selection changes after CTC construction or draft release, THE
   backend SHALL refuse reuse. Test: test_ctc_cache_retains_adapter_guard.
6. WHEN drafting is requested after release, THE backend SHALL reconstruct the
   same canonical decoder and reuse the admitted CTC object.
   Test: test_drafting_after_release_reuses_ctc.

Additionally test real decoded ZAR development audio and actual process-local
tensor memory: before/after retained CTC output/timing equality, no unused LLM
for correction-only recovery. These are preservation/resource measurements,
not accuracy, real-time factor, full-episode, VEX, CI or delivery acceptance.
