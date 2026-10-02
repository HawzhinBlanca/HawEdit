# Fresh UI Baseline And Browser Gap

Date: 2026-10-02. Source: uncommitted package
`487857046ae88bbc7f8a929e92bd65d54cd389dd11550f3fe51f43f311eeaaa8`, baseline HEAD
`372a16645d7a8558bc6cedcff34a9fbfa13f712f`. Tools: Product Design preflight/audit,
Codex in-app browser via cua_repl, documented viewport/screenshot/DOM APIs, local image viewer
and native System.Drawing image metadata. No Playwright CLI, remote upload, inference or spend.
No saved Product Design context was present. The preflight's initial incorrect script path
failed; the actual skill-local script then ran successfully. No context preference was saved.

The isolated server used temporary empty job/upload roots on 127.0.0.1:8082. It did not expose
historical private media to the audit, submit a source or connect a protected worker. The
server's exact native child PID 67492 was inspected and stopped after the browser stalled;
no Ctrl+C, console-wide event or detached launcher was used. server.log is retained.

## Steps

1. Empty desktop: DOM/accessibility tree loads the current source/settings/stages/preview
   surface. The green ready badge remains despite the unavailable protected worker. The
   1280x900 CSS viewport capture has a clipped painted region and black remainder; both
   saved desktop images are rejected as visual evidence, not accepted screenshots.
2. 320px source entry: DOM reports innerWidth 320, innerHeight 500 and scrollWidth 608.
   02-mobile-320.jpg records the returned 305x477 content region and was inspected on disk;
   source controls visibly extend beyond the left edge. This limited baseline supports the
   still-open reflow finding, not whole-screen/dimension fidelity or accessibility acceptance.
   The source dropzone is generic in the DOM, not a keyboard-exposed file-picker button.
3. Empty Generate: fresh DOM 01-empty-dom.md preceded the semantic click. It timed out in
   Input.dispatchMouseEvent; subsequent dialog reading/close attempts timed out in focus
   emulation. No dialog object, post-submit screenshot or verified validation outcome was
   obtained. The existing source's alert path is a possible explanation, not a captured alert
   message. User dismissal was requested. The temporary tab remained in browser inventory
   at the last observation. Viewport reset was attempted but not proven after the stall.
4. Generation/review/revision/export: blocked, not exercised. No selected/uploaded file,
   pipeline run, review candidates, revision or export was observed. Missing worker and
   browser interaction failure remain explicit gaps.

## Required Repair And Limits

Adopt real-byte upload/source IDs and truthful API readiness/history into the studio; make
advanced controls collapsible, source/Generate primary, and provide explicit accessible input,
contextual inline/live errors and measured/unknown states. Fix 320px reflow without hiding
overflow. Add explicit historical selection and independent private-preview error handling.
Complete authenticated review/revisions/export before creator acceptance. Preserve identity.

No new full-flow audit, WCAG AA/NVDA/keyboard, desktop screenshot, zoom, native-editor quality,
performance or release acceptance is claimed. The default 304x557 capture is retained only
as a troubleshooting observation; desktop and empty-submit capture failures must not be
substituted with old screenshots or treated as a pass. Re-run after frontend and browser
control recovery at all plan viewports, text resize and zoom, using accepted fresh captures.
