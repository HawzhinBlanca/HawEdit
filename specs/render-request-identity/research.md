# Retained Render Request Research

Baseline: bb24ec6, 2026-10-07. Parent: evidence-based-studio T3/T7, approved
by Wareen; renewed instruction: "continue the fix full fix". This unit is a
prerequisite for safe worker/revision adoption, not worker readiness or acceptance.

The existing pipeline constructs a new Clip, then reuses a retained private MP4
before resolving ASS, silence tightening, punch-ins, and the visual edit plan.
`inspect_existing_review_candidate` verifies real media, measurement, source and
clock binding, but explicitly does not verify render-input equivalence. Source,
clip ID and clock alone cannot distinguish headline, caption, camera, music or
branding changes. Reuse also reconstructs RenderResult from current settings,
which can describe choices absent from the retained video.

Keep the seven-member signed packet (D-277/D-289), canonical ASR write-once, and
immutable private bytes. Add an optional, strict render-request SHA-256 to the
existing Provenance block, which signed review already covers via editing JSON.
Legacy JSON remains readable but cannot establish cache equivalence. Compute
identity from resolved configuration, transcript/clip, actual camera and scene
inputs, assembly and caption controls, current package/model metadata, fonts,
FFmpeg bytes, and external asset bytes. Recheck before accepting reuse and before
freezing a new bundle. This is request equivalence, not evidence of editorial
quality, model execution, trusted review, or publication authority.

No dependency/model/policy switch, no HTTP readiness change, no paid calls.
BLUEPRINT sections 2-5 and 7.6; D-263 measured delivery, D-274 episode states,
D-277 private candidates, D-289 retained media inspection. Sustained independent
acceptance and trusted review remain required. Current VEX does not cover current
package bytes; do not rebind it merely to pass a test.

Actual Serena definition/reference results are recorded in the external immutable
`render-identity-map-20261007/serena-map.json`; the impact map must be finalized
from that result before editing existing source symbols.

Test-first actual pipeline/cache module: 40 cases, 33 passed, 7 failed, zero
errors/skips. All six changed-control cases reused the old MP4; the missing
request-binding case also reused it. Fresh work-directory headline revision
already changes decoded pixels; retain that positive behavior rather than invent
a second renderer. Raw JUnit: render-identity-map-20261007/test-first.xml.

Initial helper tests found a native Windows path-stat versus handle-stat ctime
difference after a real write (path retains creation time, handle exposes change
time). Existing ingest_cache._open already handles separate full baselines and
common opened identity, bounded reads/deadlines and before/after checks. Map and
reuse that helper unchanged rather than weakening mutation detection or sleeping
away the counterexample. No permissions, fixture or assertion relaxation.
