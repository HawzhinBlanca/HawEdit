# Tasks ledger — a3-park-heavy-runtime-controls
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-337; add explicit --strict-runtime / --protected-studio gating while keeping desktop WSL/Studio unblocked   (tests: test_desktop_default_bypasses_heavy_runtime_controls, test_studio_protected_mode_is_opt_in)
- [x] T2  Verify strict runtime receipt and gpu_runtime visibility controls stay intact behind explicit opt-in (VEX files untouched for lead re-pin per #16)   (tests: test_strict_runtime_flag_enforces_full_receipt_and_admission, test_gpu_runtime_strict_audit_still_rejects_visibility_overrides)

## Definition of Done (all must be true)
- [ ] Owner `Approved-by:` recorded on `plan.md`
- [ ] ADR D-337 added to `DECISIONS.md`
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
