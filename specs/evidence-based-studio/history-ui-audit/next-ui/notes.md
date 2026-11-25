# T5 Studio Adoption: Bounded Native Browser Evidence

Date: 2026-10-02. Baseline HEAD: `372a16645d7a8558bc6cedcff34a9fbfa13f712f`.
Current uncommitted package SHA-256:
`66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39`.
No accepted release, CI pass, publication, real producer run or 10/10 verdict.

## Method And Boundaries

Actual Codex in-app browser, selected browser 2, temporary tab 5, loopback port 8082.
CUA accessibility/Playwright locators drive the UI; evaluate is read-only DOM inspection.
Screenshots were saved as returned bytes and individually inspected. Temporary tab closed
and viewport reset. Audit server ran with an isolated test root at
`C:/Users/Wareen/AppData/Local/Temp/hawedit-ui-after-rjohrten`; its exact Python child was
verified and stopped without console cancellation. Test media is the existing repository
fixture `tests/fixtures/kurdish-speech-3cuts.mp4`, not private creator content.
No paid call, model inference, permissions change or user-media deletion. A private copy
was downloaded to `C:/Users/Wareen/Downloads/preview.mp4`; this is not a verified export.

The original audit's stalled tab was absent from the fresh inventory. This new session
worked; it does not retroactively turn the earlier failed interaction into a pass.
`01-before-desktop.jpg` is a fresh old-source baseline. Captures 02, 03 and 04 are
intermediate states before the final source freeze; do not attribute them to the digest
above. Captures 05 through 08 and their bounded observations use the final source.

## Observed Flow

1. Source input: repaired for tested fixture. Visible labelled native file chooser selected
   the actual 48,021-byte MP4. Reservation and PUT each returned 201; native stored bytes
   match source SHA-256 `ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15`.
   Probe reports 4,162ms, 640x360. Two same-name uploads retain distinct opaque source IDs
   `bf624fcfc03b479dbe6e630b7f9e12e2` and `c7bad4be30d64db597508fc07654863f`.
   Neither substitutes a server filename for uploaded content. Invalid README.md selection
   refuses inline as unsupported container, keeps source empty and Generate disabled.
2. Settings/reload: repaired for tested state. Preset, count and checkbox changes persist
   across reload; native server restart plus reload retains prior source and explicit job.
   Final source reload retains the second source, split preset, count five, hook enabled
   and interrupted fixture selection. No reupload, automatic generation or new token.
3. Generation/progress: blocked honestly. Generate remains disabled because protected
   worker/model readiness is unavailable. Historical interrupted work says reconciliation
   required, not automatic retry. No candidate/stage is fabricated for that job. Actual
   queued/running producer progress and unknown submission outcomes were not exercised
   in this browser session; structural tests are not execution of JavaScript fault paths.
4. History: repaired for tested fixtures. Selection is explicit; old completed data is
   unverified history, not a green delivery. Corrupt fixture record appears as a diagnostic.
   Deliberate literal script-tag candidate text stays text, with no injected script node.
5. Private preview: repaired for tested fixture. Candidate selection uses the job/clip
   scoped route; native player loaded at readyState 4, duration 4.161995 seconds. ArrowRight
   moved currentTime from zero to 0.041619 while paused. Private download bytes match the
   source fixture. Browser duration is separately labelled; independent unknown measures
   and editorial quality remain unknown. This is not real reel quality or publication.
6. Preview refusal/recovery: repaired for injected test fault. Only an isolated test
   measurement sidecar's digest was damaged; HEAD returned 409. Inline error, hidden
   stale player/download, unknown measurements and visible Retry were observed. Restoring
   the exact original sidecar (SHA-256
   `b7b793d595d89ca6cddb18ee6595c8918c6898ab59db338367c838094a87cbcb`)
   let Retry obtain 200 and load the private player again. User/reference fixtures were
   not edited. Selection of an empty interrupted job clears previous preview/stages.
7. Revision/review/export: blocked. All three controls remain disabled with explicit
   prerequisites. No authenticated signature, immutable rendered revision or verified
   bundle was created, and private download is not treated as export.

## Layout And Accessibility Scope

At 320/390/768/1280/1440 CSS-pixel viewport widths (900px height), document scrollWidth
equals clientWidth, respectively 305/375/753/1265/1425 after vertical scrollbar deduction.
No visible button/input/select/summary crossed the horizontal viewport bounds. All five
05-layout captures were inspected and accepted as bounded layout evidence. Expanded
320px settings in 06-mobile-settings also fit; keyboard Space expanded disclosure/toggled
a checkbox and ArrowDown changed the preset. Native desktop Generate height was 44px.

Skip-link Enter focused MAIN; Tab reached labelled file input. With settings collapsed,
Tab reached recovery button, SUMMARY, job select and refresh, each with a visible gold
outline. The next Tab left document focus; subsequent :focus press had no match and was
not repeated. This is bounded enabled-control traversal, not full workflow/NVDA acceptance.

Control+Equal did not change viewport, devicePixelRatio, font size or primary button height
in this browser. `zoom-attempt.json` records the no-op. Do not claim 200% text resize or
400% zoom. Declared CSS color-math tests are not rendered contrast or full WCAG 2.2 AA.
Full keyboard/media traversal, NVDA, native-Sorani copy review, complete automated browser
regressions, actual generation/error/revision/review/export and creator study remain open.

## Evidence Index

- `layout-observations.json`, `05-layout-*.jpg`: final-source five-width observations.
- `keyboard-settings-observation.json`, `06-mobile-settings.jpg`: expanded mobile state.
- `keyboard-collapsed-sequence.json`: bounded focus traversal and document exit.
- `current-source-reload-recovery.json`: final-source reload/settings/source identity.
- `seek-observation.json`, `private-download-path.json`: native private media interactions.
- `preview-refusal-observation.json`, `07-damaged-preview-refused.jpg`: injected fault.
- `preview-recovery-observation.json`: retry after original sidecar restoration.
- `interrupted-job-observation.json`: no stale media or fabricated stages.
- `invalid-upload-observation.json`, `08-invalid-source-refused.jpg`: inline refusal.
- `second-upload-observation.json`, `native-upload-evidence.json`: actual bytes/hash/probe.
- `zoom-attempt.json`: unsupported/no-op zoom interaction, acceptance gap preserved.

Source tests: `tests/test_studio_ui.py` (14 structural/color cases), revised existing
web/robustness contract cases. Node 24.15.0 syntax check passed. One-off official npm
Prettier 3.9.6 is MIT formatting tooling, not a project runtime/CI dependency. Exact
full-gate result is separately bound in T5-ui-test-evidence.json after terminal completion.
OS-private storage, per-user authentication, protected execution and full seven-phase
acceptance remain required. Test-only preview validation is not authenticated publication.

## Actual Lost-Acknowledgement Follow-Up

Same frozen package, separate isolated loopback port 8083, temporary tab 6, native CPython
3.12.10. `audit_upload_response_loss.py` subclasses only HTTP response transport: after
the unchanged receive method actually commits/probes media, it closes the socket instead
of returning the first successful PUT acknowledgement. It does not mock storage, source
validation, recovery, producer readiness or a workflow result. Real fixture bytes are
uploaded through the visible native picker and XMLHttpRequest.

Observed unknown-outcome state has empty source, inline uncertainty, disabled file picker,
disabled Upload/Generate and an enabled recovery control. Inspected accepted screenshot
`09-upload-acknowledgement-lost.jpg` captures that state. Clicking recovery makes the real
guarded status read validate the committed source; source ID is
`c34dc41f5c414213a3250dc7bf279f62`, same 48,021 bytes/hash/probe as the fixture. Source error
clears, picker unlocks, Upload stays disabled for the existing source, and Generate remains
disabled for its genuine worker prerequisite. Reload retains that same validated identity;
accepted inspected `10-upload-recovered.jpg` captures the result.

Native disk/log assertions independently find exactly one reservation, one actual commit,
one deliberately lost acknowledgement and two successful status reads (recovery and reload),
with zero repurpose requests. No second upload/publication is inferred. Files:
`upload-ack-loss-observation.json`, `upload-ack-loss-recovered.json`,
`upload-ack-loss-reload.json`, `native-upload-loss-evidence.json`; terminal server log is
`../../T5-ui-upload-loss-server.log`. The exact audit child was verified/stopped, tab closed
and viewport reset. Test storage is retained, not deleted. This is a reproducible bounded
native fault exercise, not a complete automated CI browser or reliability-corpus pass.

## Terminal Verification Binding

Exact rerun: 4,080 passed, three failed, three setup errors, zero skips in 1,017.13s;
lint/strict types/format pass across 268 files. All 14 structural/color UI cases and
67 fresh documentation-claim cases pass. Raw canonical JUnit is preserved in
`../../T5-ui-junit.xml`; bound result is `../../T5-ui-test-evidence.json`.
First full-run module-map/WIP-ledger failures are preserved in the separate first report.
Clean build, staged font absent from HEAD's archive and current-source VEX remain red.
No required CI, row completion or release verdict. This is not a completed studio.

`host-inventory.json` records the native host/runtime provenance, explicitly not a
performance benchmark. The documented CUA inventory does not expose the browser engine
version; none is guessed. Source identity is unchanged; final screenshots 09/10 supplement
the five-width captures and must not imply actual protected generation or publication.
