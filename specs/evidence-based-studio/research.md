# Evidence-Based Local Studio Research

Date: 2026-10-02. Baseline: `372a16645d7a8558bc6cedcff34a9fbfa13f712f`.
Scope: complete local creator studio, preserve its identity. One writer, sequential units.

## Evidence And Limits

The current audit is in `../product-design-audit-2026-10-02/report.md`. Its screenshots
establish layout defects, not accessibility conformance or reel quality. Source inspection
establishes integration defects, not successful model execution. Old acceptance ledgers
refer to older SHAs; they cannot establish current acceptance. No new benchmark or CI pass
is asserted. Serena mapping is captured separately in `serena-map.json`; implementation
must use actual definitions and callers, not invented interfaces.

`web.py` passes a filename instead of bytes, resolves arbitrary server paths, forwards an
unsupported `preset` directly to `run_pipeline`, and bypasses producer construction in
`pipeline.build_and_run`. Job persistence silently discards errors. Submission starts a
daemon thread. Placeholder clips, fabricated scores/durations, and render existence can
be mistaken for completion. Caption editing updates the first clip's metadata, not video.
Media lookup recursively searches filenames and falls through to filesystem serving.

`build_parser` + `build_and_run` are the existing configuration/producer boundary.
`durable_workflow` already wraps it with DBOS, a JSONL event ledger and atomic report.
The pinned installed DBOS 2.29.0 Queue API is authoritative; current online documentation
also discusses newer APIs and must not be copied without verifying installed signatures.
Existing pipeline checkpoints and workflow-control billing reconciliation remain necessary:
a coarse durable step is not exactly-once billing. D-274 distinguishes pending review,
publication and partial failures. D-263 requires measurement/reconciliation and six files.
QcRecord parses review fields but does not verify a detached signature.

## Canon And Dependencies

BLUEPRINT §§2-5 and §§8.1-8.3 remain frozen. Retain canonical ASR/model policy, write-once
transcript and timing, Sorani/RTL invariants, loopback binding, and private review defaults.
Use existing recovery, proposal, delivery and acceptance mechanisms rather than a rewrite.
The Obsidian project, durable-execution decision, Kurdish canon and honesty canon were
searched before work. Historical acceptance claims must retain their original provenance.

Blockers #1 (licensed reference audio), #3 (provider access/governance), #4 (gated diarizer
acceptance), #21 (champion licence), #24 (VEX review), and #25 (human panel/GPU runner)
require current revalidation. Planning/implementation does not accept licences, authorize
spending, fabricate labels, interrupt leased GPUs, or grant release approval.

## External Sources

- [DBOS workflows](https://docs.dbos.dev/python/tutorials/workflow-tutorial): durability
  resumes at completed steps; coarse external effects still need reconciliation.
- [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html):
  layered type/size validation, generated names and controlled storage.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/): complete-workflow AA, not screenshots alone.
- [NIST intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm):
  supporting proportion intervals do not remove episode/reviewer dependence.

Sources inspected 2026-10-02; library signatures must be checked against pinned source.

## Acceptance Mathematics Audit (Source Findings, Not Results)

`editorial_acceptance.compute_acceptance_scorecard` currently computes an IID Wald margin
from total clip count; this gives zero uncertainty for all-success data and ignores episode
and repeated-reviewer dependence. It cannot evidence the proposed cluster-aware threshold.
`evaluate_scoped_acceptance` accepts caller-supplied boolean verification flags and sufficient
sample size without evaluating editorial quality. The sustained evaluator consumes another
set of flags. These convenience summaries are not authenticated release evidence.

`visual_scorecard.compute_cluster_variance` uses episode-level ratio-estimator residuals,
which is a more relevant starting point, but its normal approximation plus clip-level Wilson
envelope is not a substitute for the preregistered episode/reviewer analysis. Leadership
assertion uses three episodes/twenty clips and a first-pass lower bound above 0.50, not the
approved release requirements (>=20 episodes/>=200 holdout proposals, first-pass >=0.95 and
lower bound >=0.90). Signoff strings and supplied competitor intervals need independent
authentication and derivation. Missing no-clip episodes must remain in accounting.

Do not lower requirements or present these old summary APIs as certification. Extend the
existing signed study machinery with current-SHA evidence verification, complete corpus
accounting and a locked analysis of episode clusters/repeated reviewer observations before
using it for a verified-candidate or sustained verdict.

## Current Security Boundary Research

The 2026-10-02 continuation checked the live WSL boundary rather than assuming the old model
inventory remained current. Missing current-source readiness correctly refused before a scan
or accepted evidence. The existing runtime and exact-size cached assets were present; direct
metadata inspection did not execute a model. Prescribed current-source revalidation is tracked
in `readiness.md`, with the detailed reviewer handoff in `security-review-packet.md`.

Additional source finding: D-260 makes the champion adapter the default, but
`OmniAsrBackend._load` explicitly documents that its adapted loader lacks the stock branch's
held-descriptor verification-to-load binding. The VEX policy's blanket checkpoint-control
claims cannot be carried onto that path from stock-loader tests or setup-time hashes. Security
review must include the default champion, not silently replace it with stock ASR or mistake
an import/readiness receipt for that review. This is a source-grounded gap, not a new exploit
measurement or qualified security attestation.

The live scan then exposed six unmatched advisory identities beyond the twelve existing
dispositions. The raw pinned-scanner report and explicitly unreviewed metadata are preserved;
its parser normalizes 27 raw rows into 18 findings across 141 installed packages. Upstream
security notices/patches were followed for all six families; no automatic "not affected"
dispositions, policy rebinding or package upgrades followed. The default champion's distinct
loader and transitive dependency behavior remain part of qualified review. Further upload
hardening changes the source fingerprint, so the saved runtime/scan evidence remains tied to
its original snapshot, never silently transferred onto newer source.

## Pinned Queue And Observer Contract

Fresh introspection in host Python 3.12.10 confirmed DBOS 2.29.0:
`Queue(name, concurrency=None, limiter=None, *, worker_concurrency=None,
priority_enabled=False, partition_queue=False, polling_interval_sec=1.0,
database_backed_queue=False, client_system_database=None)`;
`Queue.enqueue(self, func, *args, **kwargs) -> WorkflowHandle`.
No DBOS instance was launched and no stored work was resumed by this inspection.

The existing durable workflow serializes only argv and the JSON report, reconstructing
producers through the shared builder; no live producer/API-key object should enter DBOS.
The queue must be registered before launch/recovery, with concurrency one. The observer
states are started/completed/skipped/billed; billed is not a stage-completion signal. Preserve
these distinctions and sequence/attempt identity when projecting events into the studio.
Parser presets are broadcast/viral/split, resolved by the builder rather than passed as an
unsupported direct `run_pipeline` keyword. These are observed contracts for the next unit,
not claims that the studio has adopted durable queueing or producer parity yet.

## Upload Response-Loss Recovery

Current T1 source publishes a generated source directory before the final ticket write.
A lost PUT response leaves the client without its source ID; a failed ticket write after
directory publication retains valid media but records failure. There is no GET upload
status contract. Restarted `receiving` tickets also cannot distinguish live transfer from
an interrupted old process. These are inspected source facts, not runtime acceptance claims.

Repair within T1: expose guarded `GET /api/uploads/{id}`. Track active transfers in the
single-server process; report an old receiving ticket without committed media as interrupted,
never as runnable. Reconcile committed media only when bounded source metadata matches the
original reservation and the actual source length/hash verifies. Persist the recovered ready
ticket before returning a source ID. Invalid or unavailable persistence remains a contextual
refusal. Ready recovery checks hash the complete source: use this endpoint after an uncertain
upload response or refresh, not as a high-frequency progress poll. No byte-resume protocol,
cross-process upload ownership, model work, UI integration or publication is claimed.

## Read Boundary Repair Research

2026-10-02: current source package 69528dcc... at baseline HEAD plus approved uncommitted
units. Actual do_GET delegates unknown routes to SimpleHTTPRequestHandler; inherited do_HEAD
also accesses the filesystem. /media scans multiple directories recursively by filename,
including fixtures and private work. Status invents 48.14 seconds and audit_passed=true.
No verified latest publication can be derived from the legacy completion flag. Dashboard
loads Google fonts despite shipped OFL-1.1 Vazirmatn with provenance/digest. These are source
facts; earlier /README.md loopback exposure is recorded separately, not fresh audit evidence.

Serena now has 125 records, including current read helpers, constants and affected test
definitions/callers. A mistaken _candidate lookup failed; corrected _candidate_view mapping
is retained with both logs. Existing report episode_manifest.clips lists clip_id/delivery_dir;
ClipMeasurement binds media digest/size/video duration. Use those facts only for private
preview availability, never authenticated publication or speaker/editorial certification.

Approved boundary unit: BaseHTTPRequestHandler with explicit GET/HEAD routes, loopback/origin
checks, no directory fallback, no filename-only media lookup, local pinned font and unavailable
status while the protected worker is missing. Add job/clip preview routes from bounded report
manifests; refuse duplicate IDs, escapes, links, changed bytes and malformed measurements.
Snapshot verified bytes before sending headers so same-length edits cannot alter a response
after hash validation. Serialize preview snapshots with bounded acquisition, bounded media
size and storage checks; this favors correctness and does not prove target performance.
Range reads use that snapshot, strong digest ETag and exact length; HEAD sends no content.

HTTP details grounded in [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) and
[Python HTTP server documentation](https://docs.python.org/3/library/http.server.html),
retrieved 2026-10-02. This is a local studio, not an internet-facing production HTTP service.
Partial valid ranges are 206, valid unsatisfiable ranges 416, malformed/multiple ranges are
ignored with full 200, and If-Range mismatch uses full current bytes. Range is ignored on HEAD.
Private preview does not supply a verified export. Sidecars, authenticated delivery, job migration,
UI adoption, OS ACL preflight and complete browser/accessibility acceptance remain required.

Offline-font packaging research found the source binary was not installed by the wheel and
was absent from its SBOM. Embedded font metadata gives the same copyright/OFL-1.1 identity
as the [pinned upstream v33.003 notice](https://github.com/rastikerdar/vazirmatn/blob/v33.003/OFL.txt),
retrieved 2026-10-02. Preserve the binary/digest and existing Noto assets; add Vazirmatn's
copyright/provenance to wheel data and a distinct SBOM package/relation. The installed path
uses environment.resolve_installed_hawedit_data's existing RECORD authentication, then the
same bounded/stable pinned-font read. A missing/altered checkout font never falls back.
The native PathDistribution/RECORD layout probe controls distribution discovery only; it is
not clean-install or qualified legal/security acceptance. Full release/CI obligations remain.

The first snapshot run reproduced differing Windows CPython 3.12 lstat/fstat ctime values
for the unchanged font: lstat reported creation while fstat reported modification. Use the
stable Windows birth timestamp plus inode/size/mtime/link count; retain POSIX change time.
Snapshots still hash complete bytes and check records/file identities before headers. The
large texture probe initially lacked audio, so the real measurement engine refused it;
add an actual audio stream to the test media, without relaxing measurement requirements.
Neighboring local origins and duplicate Origin headers also reproduced unintended read access;
the guard now permits only none/same-origin fetch metadata and a single exact Origin.

While the T4 exact gate runs against frozen source, independent acceptance research reproduced
order-dependent comparison means, repeated-reviewer inflation, public-seed unblinding and an
unsupported 10/10 acceptance by the old scorecard helper. These are explicitly synthetic
mechanism counterexamples, not evaluation data. statistical-acceptance-research.md and its
three generated JSON observations record the commands' source/runtime and limits. Serena
now has 151 records. Repair these evidence/math boundaries before relying on any human
study verdict; the current helpers cannot authenticate the user plan's sustained acceptance.

## Non-Destructive History Adoption

Current source inspection confirms JobManager loads job.json into memory, silently discards
all exceptions, and returns legacy completion/progress/clip scores unchanged. HTTP job reads
therefore cannot establish durable status, publication, measurements or active execution.
Metadata-only edit_caption still returns success without a render. The approved T3/T4/T7
repair requires adopting truthful reads before worker/UI integration, not certifying old data.

Use a bounded read-only historical projection of actual persisted files, with stable
single-link JSON reads through the existing artifact boundary. Preserve job/media bytes and
bind each valid historical view to its raw record digest. Completed/review records stay
unverified-historical; queued/running records require explicit recovery reconciliation and
never auto-enqueue. Keep terminal failure/cancellation visible. Do not echo server paths,
tokens, raw options, fabricated scores/durations or unsourced stage percentages. Private
candidate IDs come only from the scoped report manifest, not the legacy cached clips list;
playback still verifies measured media separately. Missing/invalid report evidence is visible.

Keep /api/jobs as a list for existing callers. Add /api/history's versioned jobs/diagnostics
envelope and expose history availability/diagnostics in status; unreadable or truncated
enumeration must not look like an empty complete history. Detail reads reflect disk changes,
not a stale cache. Until immutable measured render revisions are connected, the old caption
API refuses with revision_required, retaining every record and canonical transcript byte.
Programmatic legacy JobManager execution is not certified or enabled by this unit. Its
daemon/persistence replacement still requires the protected worker and authoritative lifecycle.

Serena has 157 definition/reference records; T3-history-serena.log maps stable record readers,
current HTTP/edit test callers and status tests. Existing handler maps remain applicable to
their unchanged dispatch signatures. No new runtime dependency or delivery-engine edit.

Native test-first hardening confirms: failed-record bytes must count toward scan limits;
portable IDs may contain spaces/%/# and require component URL encoding; malformed entries
must not disappear behind a successful empty jobs-list response; bounded JSON depth can
raise native RecursionError; lone-surrogate JSON strings cannot become UTF-8 HTTP responses;
and accepted native HTTP sockets had no default timeout. Preserve these red logs. The shared
JSON reader now returns contextual refusals for decoder recursion/transport failures, text
validation refuses invalid Unicode, and handler setup configures native 60-second socket
timeouts before request processing. CPython 3.12.10's actual inherited setup signature/source
was inspected before adding the override. The native protocol test observes the actual socket
and exercises disk refresh/origin refusal; it is not browser or zero-hang corpus acceptance.
Original mistaken space-ID and http helper/import collision tests are recorded and corrected
from native contracts without reducing payloads or weakening old fixture/golden assertions.
Serena has 173 definition/reference records. Legacy programmatic persistence/daemon execution
remains unaccepted; this unit does not pretend its writer failures or producer checkpoints
are repaired. The protected lifecycle remains a subsequent required integration.

## T5 Studio Adoption Research

Serena now has 182 symbol/reference records, including the existing DASHBOARD_HTML constant
and its two test callers. Current source confirms filename-only submission, modal alerts,
automatic latest-history selection, invented progress and direct preview-as-export links.
Fresh isolated capture history-ui-audit/next-ui/01-before-desktop.jpg was inspected locally
on 2026-10-02; its empty source coexists with a ready badge and an empty media player.
The previously stalled temporary tab is now absent from authoritative browser inventory.
No old screenshots substitute for this fresh source capture.

Retain the stdlib server and vanilla embedded frontend. Extract the rewritten UI constant
into studio_ui.py, keeping web.DASHBOARD_HTML import compatibility; no new runtime package,
network asset, backend route, model policy or publication authority. Actual file bytes use
reservation POST plus streaming PUT; upload progress is byte-transfer progress only.
Persist opaque reservation/source IDs and exact generation payload/token before submission.
Unknown submission outcomes must retain that same request, never silently mint a new token.
Native file input and details/summary provide keyboard semantics without custom widgets.
History requires explicit selection, diagnostics and historical/unverified context. Clear
stale preview/measurements before selection and ignore superseded asynchronous responses.
Current /api/status refuses the missing protected worker; do not present it as ready.
Unconnected rendered revision/authenticated approval/export remain visibly unavailable.

Primary sources consulted: MDN input/file and XMLHttpRequest/upload document browser-selected
File objects and byte progress versus request outcome; W3C Understanding WCAG 2.2 Reflow
and Status Messages ground 320px shrinking, focus and live status. Sources:
https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file
https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/upload
https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
Static HTML/contract regressions are not JavaScript execution or AA acceptance. Supplement
them with current in-app browser actions, actual decoded fixture upload and fresh screenshots;
report browser gaps, native-editor copy review and NVDA/zoom acceptance separately.
## T5 Full-Gate Documentation Snapshot Correction

The first final-source UI gate reported 4,078 passed, five failed, three setup errors,
zero skips in 1,018.77s. Fourteen new UI cases passed. Two additional failures are real
new-module README/PROGRESS omissions in pytest's collected document snapshots. The new
module map and WIP M9.43 entries were added after collection had loaded those files;
tests/test_claims.py reads README/PROGRESS once at module import. Preserve the original
failure report rather than changing tests or relabelling the first gate as green.

A fresh complete tests/test_claims.py run reads current entries and passes all 67 cases
in 11.10s. This is not the exact gate or CI. Freeze source and tested living documents
before the next exact full run; do not edit collection-time docs during verification.
The first canonical JUnit is preserved as T5-ui-first-junit.xml, with bound first-run
metadata in T5-ui-first-test-evidence.json. Other first-run failures remain dirty-checkout
build, staged font notice absent from HEAD archive and current-source VEX binding.
