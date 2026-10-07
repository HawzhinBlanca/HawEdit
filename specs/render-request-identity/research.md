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

## Retained Metadata Follow-Up

Clean candidate774e5639b1ecf6e290d70299dcd1b3875eb57695 completed the exact
gate:5111 cases,5109 passed,2 failed, zero errors/skips; source unchanged.
One regression is test_unreviewed_render_is_retained_privately_for_review:
legacy unsigned QC metadata was incorrectly included in pixel request identity.
QC is separately checked by assert_renderable and authenticated publication;
it must not alter equivalent pixel requests or promote retained private bytes.
The other failure is current-source VEX qualification (#24), not silently rebound.

An actual decoded two-utterance fixture with silence threshold25ms/target5ms
records295ms removed in its editing JSON. Identical replay returns0ms and
unretimed words; requested duration4162ms differs from retained plan3867ms.
Inspector validates stored Clip/VisualEditPlan but returns only measurement,
so the caller loses the actual metadata. Single-utterance negative control has
no trim and exact agreement. Original packet/transcripts are byte-identical.
External corrected test-first module fails both exact metadata and duration
assertions; initial erroneous serialized-key test is preserved, not counted as
a product-duration counterexample. No neural/editorial/publication claim.

Actual Serena map retained-metadata-map-20261007/serena-map.json completed
10:12:19UTC on unchanged current source: run_pipeline, cache inspector and
tighten_clip. Return a typed nonauthorizing retained Clip/edit plan/fresh physical
measurement record, keep every inspection guard, and use the retained plan's
precise output duration. Exclude only post-render QC from pixel identity; QC
refusals and raw signature/publication checks remain. No silence algorithm edit,
canonical ASR edit, sidecar rewrite, approval, dependency or HTTP readiness change.

Repository test-first: complete retained-cache module44 cases,41 passed,
3 failed,0 errors/skips, JUnit168.672s. Correct failures are exact retained
metadata, precise retained output duration, and unchanged private reuse with
unsigned QC metadata. Controller178.2106299s confirms frozen watched source/
HEAD/package/status. Raw retained-reporting-candidate-20261007/test-first/
terminal.json, XML a5ec89eeef10a69d949805eb45f1921b7a4a022f0b3b87de44268035c93b17e3.
