# Tasks ledger — credentials-panel
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  `HF_TOKEN` becomes a stored credential: constant, `validate_hf_token` against the HF
          whoami endpoint with the same bounded-response and header-safety rules
          `validate_gemini_key` uses, and `credential_status` reporting it.
                                    (tests: test_an_hf_token_is_verified_before_it_is_stored,
                                            test_an_hf_token_response_is_bounded_like_the_gemini_one)

- [x] T2  The token reaches the download: `Download` protocol gains keyword-only `token`,
          `model_fetch` reads it via `read_credential` rather than `os.environ`, and every stub
          is updated.               (tests: test_a_stored_hf_token_is_honoured_without_the_environment,
                                            test_the_gated_download_receives_the_token_explicitly)

- [ ] T3  `setup_panel` — one window, masked fields, verify-before-store, `mask()`-only display,
          per-credential "this unlocks" line including the billing caveat for #3.
                                    (tests: test_the_panel_never_displays_an_unmasked_secret,
                                            test_a_credential_that_fails_verification_is_not_stored,
                                            test_the_panel_names_what_each_credential_unlocks)

- [ ] T4  Headless fallback to the existing terminal panel, and the `hawedit-setup` console
          script.                   (tests: test_no_display_falls_back_to_the_terminal_panel,
                                            test_the_setup_console_script_is_declared)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] No secret appears in any log, title, traceback or committed file
