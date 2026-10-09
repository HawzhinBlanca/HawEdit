# Immutable Revision Artifacts

Baseline aeca0ae518a30832ad7bd3af0446183831c83c99, package
5c351c985cbcaef8570fbde2de0bdfd463f49ec66d207a9a4a97dde008179e73.
Read project vault canon, approved evidence-based-studio plan step6, and actual
revision/render/publication source. Canonical transcript, sentence anchors and
caption clocks must remain unchanged except legal outward boundary padding.

Actual Serena definitions/references, unchanged source/ref/status:
C:/Users/Wareen/HawEditRevisionImmutability-aeca0ae-20261009/serena-map.json,
8f5e6c6f44c3ed232438f614cecc699094ced12b3a36da108e06e8f7c3d70054,
12pairs; supplementary historical overwrite test and render publisher2pairs,
C:/Users/Wareen/HawEditRevisionCollisionTests-aeca0ae-20261009/serena-map.json,
eaaa9eb99fe7c42f84505ee1508f961a476a41f2480b2d7c96e42645a2b3b8d8.
Original mapper commands gone/sessions80526 and56828 closed.

Confirmed: both commit functions overwrite a reused revision JSON identifier.
Both render functions write final ASS before encoding and overwrite SRT/EDL.
Their RenderError cleanup unlinks final MP4 even when render_clip refused a
competing artifact. render_clip already uses atomic no-replace hard-link
publication and cleans only its own staging file. Caller cleanup defeats it.

Existing style/boundary revision tests decode real fixture media, but the old
duplicate-ID test explicitly requires overwrite. Keep that named test/coverage
and strengthen it to preservation/refusal under D-321; do not delete or skip it.
This deliberately supersedes its historical behavior, not a fixture/golden edit.

This unit repairs private CLI/shared revision integrity. It does not enable the
HTTP editor, authenticated approval/export, paid generation or model admission.
Those and BLUEPRINT8.1-8.3, D-263/D-274 and AC-1-AC-12 remain required.

Further inspection after83revision cases passed found a same-ID render race:
two callers can pass pending status/preflight before either publishes output.
Only one may own lifecycle writes. Add a persistent exclusive render claim;
unknown/previous claims require reconciliation, never a guessed-PID or age-based
automatic release. This is private CLI uniqueness, not complete DBOS recovery.
Current actual5pair helper/render map, unchanged source/ref/status:
C:/Users/Wareen/HawEditRevisionRenderClaim-20261009/serena-map.json,
ac25d980727a7ac9371d317fef165660004a4c3dc80045cac05fc15db8c244d9.
Original mapper gone/session50553closed. Add real competing callers and retained
claim cases test-first before adoption; no renderer mocks or source authority flags.
Previous exact full gate5917pass/1historical-qualified-policy binding failure
is retained, not self-rebound (#24/#25). No security/CI/10/10 claim.
