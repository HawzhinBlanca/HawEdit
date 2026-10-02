# Current Readiness Observation

Observed 2026-10-02 on baseline `372a16645d7a8558bc6cedcff34a9fbfa13f712f` plus
uncommitted studio work. This is inventory, not a performance or production benchmark.

- `Get-CimInstance Win32_Processor`: AMD Ryzen Threadripper 3990X, 64 cores/128 threads.
- `nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv`:
  two RTX 3090 Ti, driver 610.88, each 24,564 MiB total; 1,666 MiB used at observation.
  Memory use does not prove a safe GPU lease. No GPU/model job was launched.
- `.venv/Scripts/python.exe`: CPython 3.12.10, Windows 11 build 26200.
- Installed metadata: DBOS 2.29.0, pytest 9.1.1, ruff 0.9.6, mypy 1.15.0, torch
  2.13.0+cpu. transformers, opencv-python, pyannote.audio, omnilingual-asr distributions
  absent in this Windows venv. This does not establish the state of the WSL runtime.
- The real-media upload regressions invoke installed ffprobe and decode a first video frame
  through ffmpeg. This is input validation, not end-to-end Sorani quality evidence.
- Checkpoint hashes, model licence acceptance, current provider governance/credentials,
  WSL readiness, VEX and registered CI/GPU runner still require current validation. Never
  infer them from a directory name, old pass or available GPU memory.

Gate logs: `gate-T1.log` (initial) and `gate-T1-final.log` (final checkpoint).
A focused test pass does not substitute for the gate.
No current exact-SHA CI, human study, delivered-reel benchmark or 10/10 verdict claimed.

## Completed Registry Report

`.venv/Scripts/python.exe -m hawedit.models` completed; full output in
`model-readiness.log`. Registry reports 9/15 available. Canonical OmniASR's current-source
WSL readiness receipt is missing, Community-1 not downloaded, Gemini credentials absent.
Qwen embedding/reranker, VideoChat3 and TimeLens checkpoint bytes passed integrity checks.
This does not prove their application loaders, a safe GPU lease or reel quality.
That report predates final upload hardening and was bound to package digest
`2bf679cfbde9e4c61d10cb3816c93da9407c0e1ed3a2821fa3471feb53c288a3`.
It is inventory evidence, not a readiness receipt for the final source digest below.
OpenCV is importable through `opencv-python-headless` 4.12.0.88; the absence of the separate
`opencv-python` distribution above does not mean OpenCV itself is missing.

Selected ffmpeg: Windows PATH build 8.1.1-full_build-www.gyan.dev, not a HawEdit-fetched
generation. `models/revisions.json` SHA-256:
`f4cdcd1e1422cb32bd53a22b2edbcdb3f70cbdc88ee3bf56c472afedee4a9b3c`.
`models/sources.json` SHA-256:
`811475984a911e6ce579f0dda5bd04d2f0c65d7574b6fb8974fb21363af07091`.

`gh run list --commit 372a16645d7a8558bc6cedcff34a9fbfa13f712f` returned no runs;
`gh pr status` returned no associated/current PR. No CI acceptance inferred.

## First Full Gate

`bash scripts/verify.sh`: lint, strict types and format pass; pytest reports 3,816 passed,
four failures, three errors, 982.97s. The failures concern new module documentation,
clean-checkout wheel building and the VEX source digest. No tests were skipped or weakened.
Documentation is being corrected. The old VEX expires 2026-09-08 and is not rebound or
redated without a qualified review (#24). No ledger row is accepted. Logs created inside
the checkout also make it dirty for reproducible-build tests; subsequent live logs belong
outside the checkout and are copied as evidence only after the run, not treated as source.

## Final T1 Checkpoint Gate

After documentation and upload hardening, the exact `bash scripts/verify.sh` exited 1.
Lint, strict typechecking and format passed across 254 files. Pytest reported 3,820 passed,
two failures, three errors and one warning in 964.77 seconds on the recorded host/runtime.
Full output: `gate-T1-final.log`; the live log was outside the checkout during execution.
The 85 focused upload/documentation regressions also passed. No test was skipped or weakened.

- `test_the_wheel_contains_every_file_the_audit_report_says_it_does` failed because
  reproducible release building correctly refuses the uncommitted checkout.
- Three build-fixture errors have that same clean-checkout prerequisite:
  `test_two_builds_of_one_commit_are_byte_identical`,
  `test_every_entry_carries_the_commits_timestamp_not_the_clock`, and
  `test_build_script_reports_the_hash_locked_private_builder`.
- `test_checked_in_policy_binds_current_lock_and_assets_and_closes_report` failed because
  the reviewed VEX digest does not cover the changed source. Qualified re-review under
  blocker #24 is required; blindly rebinding its digest/date would fabricate an attestation.

Final source package digest:
`52d23b1833eb3d761b4a6781a60ac43bd66b2cdca1b45fa1fc05c273bbebc8f0`.
Baseline HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`; source is uncommitted.
No ledger row is flipped, no exact-SHA CI pass exists, and no verified-candidate or 10/10
verdict is awarded. T1 is an unaccepted API upload foundation; frontend/generation adoption
and subsequent sequential tasks remain unimplemented. That turn stopped at the red-gate
checkpoint pending security review and clean committed-source verification. This historical
stop does not grant acceptance or prohibit further test-first repair of the unaccepted unit.

## Continuation: Current WSL Readiness And Live Security Check

The next goal turn made a fresh live observation rather than repeating the red-gate summary.
`wsl.exe --list --verbose` reported Ubuntu running (WSL2). A metadata-only probe of the existing
Ubuntu environment reported Python 3.12.0, OmniASR 0.2.0, torch 2.8.0, transformers 4.57.6,
fairseq2 0.6 and qwen-asr 0.0.6. This alone did not satisfy canonical readiness.

The prescribed `.venv/Scripts/python.exe -m hawedit.wsl_setup --distribution Ubuntu` exited 0.
It reused complete generation `Ubuntu-33853eeafb05ecf1b998dc84`, rehashed the canonical
43,546,500,168 bytes, verified the 141-distribution lock, imported worker dependencies and
reported two CUDA GPUs. It ran no model inference. Host/runtime are the recorded Threadripper
3990X, two RTX 3090 Ti, driver 610.88, host CPython 3.12.10 and WSL Python 3.12.0.
Evidence: `current-wsl-readiness.log` and the verbatim `current-wsl-receipt.json` (SHA-256
`57ab593ceea33e027eb96e47dd4834d4a9e5100760a4f2b41fb9b14fde8d8825`). The receipt binds the
current `52d23b...ebc8f0` source. Earlier missing-receipt observations remain historical facts,
not the current readiness state. No throughput, champion inference or quality claim follows.

The subsequent exact live vulnerability command (`hawedit.wsl_vex_gate --distro Ubuntu
--timeout-seconds 300 --evidence <new-path>`) exited 1. It completed the live check but refused
the expired VEX, changed source and six additional unmatched findings in accelerate,
transformers and urllib3. No accepted evidence file was created. Full terminal refusal:
`current-live-vex.log`; identities and unresolved triage are in `security-review-packet.md`.
The default champion-loader verification-to-load gap was also grounded in five additional
Serena caller lookups. Security approval, full gate, exact-SHA CI and all product acceptance
remain outstanding. These observations preceded the upload repair below; no harness was edited.

## Continued T1 Repair: Malformed Persistence And Lengths

Nine new regression cases reproduced unhandled or misclassified malformed record fields and
5,000-digit Content-Length headers. JSON record reads are now bounded during I/O, not just
by a preceding stat. Stored filename/container identities are validated consistently with
new reservations; non-string state values, overflowing/nonpositive clocks and malformed JSON
produce contextual upload refusals. Length headers are bounded before integer conversion.
No integer-conversion safety limit was relaxed. No old assertion or fixture was changed.

Four additional Serena lookups map `_record`, `begin`, `receive` and `_request_length`
callers, bringing evidence to 32 records before edits. Caller obligations include reservation
capacity accounting, transfer, describe/source resolution, HTTP POST/PUT and upload regressions.
The first mapping run hit a transient write error after two saved records; its terminal
outcome was confirmed and a sequential retry completed the remaining records.

New source digest: `a3cf9e5e11d006e816cf8a98880043367d3d95dc978873221082b22b88521dbd`.
The copied WSL receipt and diagnostic scan are explicitly historical `52d23b...` evidence,
not readiness for this changed source. Source-bound readiness must be refreshed after source
stabilizes; neither security policy dates nor its reviewed digest are rebound automatically.
The exact full repository gate was rerun for this repair. Terminal result: exit 1;
3,830 passed, two failures, three errors and one warning in 958.80 seconds on the recorded
host. Lint, strict types and formatting passed across 254 files. The 95 focused upload /
documentation cases passed before that run. Full output: `gate-T1-hardening.log`.
The two failures are the dirty-checkout wheel refusal and current-source VEX digest binding;
the three errors are the same clean-checkout build fixture prerequisite. No new regression
failure remains in this run. This is not a green gate and does not close a ledger row.
The qualified review remains necessary for acceptance, but engineering continues within T1
without bypassing the gate, switching the champion or claiming completion.

Read-only GitHub revalidation: the repository runners endpoint returned zero registered
self-hosted runners. Latest three main runs were skipped at `348355479a5517b454d673cf36c46abb2c3fe741`,
not baseline HEAD or these edits. The API result is preserved in
`repository-runner-observation.json`. This is a narrow repository observation, not proof about
all possible organization/enterprise infrastructure. No runner registration or workflow
dispatch was attempted and no applicable current-SHA CI pass is inferred.

## T1 Response-Loss And Atomic-Commit Recovery

The preceding goal turn made source and evidence progress. The continuation inspected the
current tree and repaired a further T1 gap: an upload committed successfully but with a lost
response or failed final ticket write had no supported recovery lookup. Ten newly added
cases failed before implementation. Existing upload assertions, fixtures and harness were
preserved. Guarded GET status now verifies bounded committed metadata, reservation identity
and the complete source length/hash; it repairs a ready ticket before acknowledging success.
Live receiving, interrupted old transfer, failed and expired reservations are distinct;
none of the latter yields a source. Same-length altered media and mismatched/missing evidence
refuse recovery. An injected persistence outage returns HTTP 503, never a source ID.

All 71 focused cases in `test_studio_uploads.py`, `test_web.py` and
`test_robustness_audit.py` passed. A separate real loopback HTTP POST/PUT/GET smoke check,
including store reconstruction and actual byte/hash comparison, exited 0; log:
`upload-recovery-loopback-smoke.log`. Fixture: 48,021 bytes, SHA-256
`ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15`.
That check discarded the acknowledgement; it did not inject a dropped network connection,
execute a model or publish a deliverable. No browser/visual acceptance claim follows.

The full gate's first invocation resolved `bash` to WSL and refused before checks because of
Windows-interpreter carriage-return path handling; log:
`gate-T1-recovery-wsl-shell-refusal.log`. Reinvoking the same `scripts/verify.sh` with the
installed Git Bash used by prior Windows gates reached strict typing, which caught two new
typing issues; log: `gate-T1-recovery-typecheck-red.log`. These were repaired without changing
the harness or assertions. The subsequent exact full gate passed lint, strict typing and
formatting across 254 files, then terminated with exit 1: 3,840 passed, two failures, three
errors, one warning and zero skipped in 949.76 seconds. The same dirty-checkout wheel refusal,
three dependent clean-build fixture errors and VEX source-digest mismatch remain; no upload
regression failed. Full log: `gate-T1-recovery.log`. The generated
`upload-recovery-test-evidence.json` independently reads the canonical JUnit report, verifies
all 38 upload cases have no failure/error/skip, and records report/log hashes, source identity,
runtime versions and the unaccepted verdict. No hand-written gate evidence or ledger flip.
All gate, Serena and smoke-check processes launched for this milestone are terminal.

Current package digest: `29031bcdf7ec18d980ee614b7801bc72c9535bf360c1b650f1c15ee8bf6e9ec0`.
The saved WSL receipt and vulnerability scan still bind historical `52d23b...`, not this source.
No VEX dates/digest, model policy, dependency lock, enforcement file or ledger row changed.
Residual limits: no partial-byte resume, no multi-process upload lease, and full-file recovery
hashing holds the single-server store lock; this endpoint is not a frequent progress poll.
Frontend/generation adoption and T2-T10 remain unimplemented and unaccepted.

## T2 Strict Request And Evidence Projections

The next sequential unit added `studio_generation.py`: versioned source-ID requests, strict
bounded options, actual shared-parser preset resolution and immutable preparation snapshots.
Configured production argv selects champion ASR, discovery/judging, diarization, visual reading
and temporal grounding, but no producer is constructed in preparation. Provider selection is
not spending/governance authorization. Durable identity still needs actual model/runtime and
owner-policy bindings in T3.

The web repurpose endpoint now refuses filename/server paths instead of invoking the legacy
daemon. A valid real uploaded source receives HTTP 503 `studio_runner_unavailable`, explicitly
stating no job was queued. This is an intermediate integration gap, not working generation.
Old frontend, programmatic JobManager, historical reads, recursive playback and metadata-only
caption edits remain unaccepted and must be replaced/adopted by subsequent units.

Projections verify real artifact length/hash against typed measurements, retain unknown scores,
and distinguish private review from publication. Stage projection retains sequence/state/attempt
and never treats billing as completion or invents within-stage percentages. Raw episode outcomes
are observations, not authenticated publication; label them accordingly before frontend adoption.
No caption/speaker/editorial quality certification follows from a matching preview hash.

All 167 focused cases passed (`T2-boundary-focused-final2.log`), including 29 new generation
cases and the existing upload/web/robustness/documentation cases. A separate real loopback
POST/PUT/source-ID request smoke exited 0 (`T2-boundary-loopback-smoke.log`): upload 201/201,
valid generation 503, raw-path generation 400, zero jobs created. Source: 48,021 bytes,
SHA-256 `ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15`.
Independent ffprobe 8.1.1 found video duration 4.120000 seconds vs audio/container 4.161995;
`fixture-clock-observation.json` records that correction to the new test expectation. No fixture,
golden or old quality assertion was altered. Legacy raw-path-success HTTP assertions were
replaced by the approved stricter refusal contract; every original test name/count remains.

Initial full-gate attempts stopped at strict typing, then lint, on parser error-policy typing.
Both logs are preserved (`gate-T2-boundary-typecheck-red.log`, `gate-T2-boundary-lint-red.log`).
A narrow structural protocol now describes the actual stdlib property without type/lint ignores
or global stderr redirection. The subsequent exact gate terminated with exit 1: 3,869 passed,
two failed, three errored, one warning and zero skipped in 953.11 seconds on the recorded host.
Lint, strict typing and formatting passed across 256 files. Remaining failures are the same
dirty-checkout wheel refusal, three dependent clean-build fixture errors and VEX source binding.
No generation/upload regression failed. Full log: `gate-T2-boundary.log`. The generated
`T2-boundary-test-evidence.json` reads the canonical JUnit report, confirms all 29 generation
and 38 upload cases passed without skips, and records source/report/log hashes and versions.
This is not a green gate; no row was flipped. All launched gate, Serena and smoke processes
are terminal. No gate report, enforcement file or acceptance policy was manually edited.

Current package digest: `122ca64f6b9665951b353e2ea9f3fd8a2355be0bfb354b200ef82bd662c0b41c`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, source uncommitted. Historical WSL
readiness/scan still bind `52d23b...`, not current source. VEX, CI and human acceptance remain
open; no model inference, paid call, publication, harness edit or ledger flip occurred.
Serena now has 64 records; six additional T3 lookups found a production billing-recovery gap,
documented in `durable-studio-research.md`. Research is not an executed recovery guarantee.
That research also confirmed unlisted filesystem serving through the legacy static fallback
using only `/README.md` on a temporary loopback server; no secret was read. The refusal repair
is still required, alongside removal of fixed `/api/status` duration/quality claims. The studio
must not be treated as accepted for publication while these old read surfaces remain.

## T3 Submission Outbox And Queue Mechanism

The next sequential unit implements an immutable SQLite submission/token outbox and the
actual pinned DBOS 2.29.0 serial queue. Submission identity binds the finalized source,
effective configuration, normalized arguments, worker name and supplied execution-binding
digest; that digest alone is not certified runtime readiness or owner authorization. Native
SQLite transactions prevent partial token/job writes, reject conflicts and expose corruption
or bounded lock failures. A confirmed dispatch cannot be downgraded by a late error.

Queue reconciliation validates the recorded worker, queue and job-ID-only inputs, reuses the
same execution and refuses persisted nonserial queue settings without overwriting them.
Actual SQLite/DBOS tests cover lost local acknowledgements and two-process recovery after
abrupt exit following enqueue. The probes perform no inference or paid work. These tests
do not establish recovery inside a producer, exactly-once billing or verified publication.

Test-first collection failures and subsequent regression failures remain in the T3 logs.
The native JSON depth experiment corrected a faulty test assumption: CPython's JSON decoder
limit is not simply its Python recursion limit. Bounded deep-input tests first demonstrate
the actual native refusal, then assert contextual storage/preparation errors. No existing
assertion, fixture, golden, recursion limit or enforcement policy was weakened.

The exact full gate terminated with exit 1: 3,899 passed, two failed, three errors, one
warning and zero skipped in 1,035.03 seconds. Lint, strict typing and formatting passed
across 260 files. Failures remain dirty-checkout wheel refusal, three dependent clean-build
fixture errors and current-source VEX binding. The canonical JUnit reader independently
confirmed all 23 submission, seven queue, 29 generation and 38 upload cases passed without
skips. The intermediate focused run also caught missing module evidence in the PROGRESS
WIP row; documentation was repaired before the full gate, without changing the test.

Evidence: `T3-outbox-test-evidence.json` and `gate-T3-outbox.log`. Canonical JUnit SHA-256:
`d69b54a2411ec129c1f9beb48fd6f55807a2a7aa97c68cc783563a8814aa5206`.
Gate log SHA-256:
`06cdedd3c3b63d15b78e39f8d4bba1ec4f17c77dbfb846795bf723dcc211aef1`.
Current package SHA-256:
`830f77b699f6d38af61bf7c14e323b66751909d9a1fbcf0052a039a6152b8b28`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, source uncommitted.
Observed host runtime: CPython 3.12.10, SQLite 3.49.1, DBOS 2.29.0, pytest 9.1.1,
ruff 0.9.6 and mypy 1.15.0; hardware inventory above is unchanged historical provenance,
not a new performance measurement. All launched gate, probe and Serena processes are terminal.

Serena now has 86 definition/reference records. `protected-worker-research.md` identifies
shared-builder transport injection and a missing output/thinking budget bound in current
provider configuration. Registered callback metadata cannot certify its security controls.
Next implementation must provide a protected worker with actual runtime/governance checks,
pre-request billing intent, uncertain-outcome reconciliation and artifact checkpoints before
API/read/non-destructive migration adoption. HTTP generation still explicitly refuses a
missing runner. No cloud call, licence acceptance, authenticated publication, browser/NVDA
acceptance, model-quality benchmark, harness edit, commit, applicable current-SHA CI or
ledger flip occurred. Historical WSL/scan evidence does not bind this changed source.
The complete seven-phase program remains active; this mechanism is not an accepted studio,
verified candidate or 10/10 verdict.

## T3 Billed Transport Mechanism

The next sequential unit adds studio_billing.py and an optional keyword-only judge_transport
to the shared builder. The guard commits a native SQLite intent and conservative integer
reservation before generation, retains uncertain outcomes, and records bounded confirmed
response/hash/usage evidence before returning it. Authorization pools span jobs; policy drift,
corrupt reservations, foreign databases, expiry and ambiguous responses refuse execution.
Distinct repeated-content occurrences preserve Path A's K calls instead of fabricating votes.
Confirmed deterministic re-entry reuses each response without another generation request.

These are mechanism results, not real provider bills or spending authorization. Native SQLite,
real loopback HTTP and a second process that abruptly exits after receiving a response exercise
actual atomicity/recovery. Shared-builder tests use the unchanged decoded media fixture and
bound manual transcript, with controlled local discovery/judging responses. No model inference,
ASR quality, independent editorial quality, authenticated delivery or genuine account cost was
measured. The guard is not yet connected to HTTP production or the actual protected worker.

Test-first and reproduced integrity/type/schema failures are preserved in the T3 billing logs.
The oversized automatic pytest case ID failure on Windows was repaired using short IDs without
changing payloads. Existing flat test helper imports avoid a strict-mypy duplicate-module error;
no harness configuration, old assertion, fixture, golden or security policy was weakened.

The exact full gate exited 1: 3,943 passed, two failed, three errors, one warning and zero
skipped in 1,058.88 seconds. Lint, strict typing and formatting passed across 262 files.
Canonical JUnit independently confirms all 44 billing, 23 submission, seven queue,
29 generation and 38 upload cases passed. Remaining failures are dirty-checkout wheel
refusal, three dependent clean-build fixture errors and VEX source binding. No row was flipped.
Evidence: T3-billing-test-evidence.json and gate-T3-billing.log. JUnit SHA-256:
`8c783fb67a82cf8bc9e8b264b4f67dd1fc236fb21cd9f9ddbc0424bf9dce2222`.
Gate log SHA-256:
`ba4cf6362f4fa8296a4c2b703f65aee06e9d9df98ee9be6264a81d5933ff09df`.
Current source package SHA-256:
`69528dccd42f592175a3d09c41debcd072673e5d0c9dca71bff62a7e49fcc3a4`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, source uncommitted.
Observed runtime remains CPython 3.12.10, SQLite 3.49.1, DBOS 2.29.0, pytest 9.1.1,
ruff 0.9.6 and mypy 1.15.0. Historical hardware provenance above is not a new performance
measurement. All launched gate, local-provider probe and Serena processes are terminal.

Serena now has 116 definition/reference records. protected-worker-research.md records
remaining authenticated policy, live provider prompt-overhead/thinking/pricing semantics,
runtime/governance preflight, private storage and checkpoint obligations. Optional screeners
use separate transports and are not guarded by judge injection. The ASR WSL bridge does not
move visual producers into WSL. Historical WSL receipts/scans and expired VEX do not bind
this changed source. Legacy filesystem fallback and fixed status claims remain release blockers.
No paid request, licence acceptance, cloud governance change, publication, harness edit,
commit, current-SHA CI pass, browser/NVDA acceptance or ledger flip occurred. The complete
seven-phase program remains active; this is not an accepted studio or 10/10 verdict.

## T4 Private Read Boundary Checkpoint

The next sequential unit replaces generic GET/HEAD filesystem serving with explicit routes,
origin/Host checks and manifest-listed job/clip private previews. A bounded single-consumer
snapshot hashes and copies actual measured MP4 bytes before serving ranges, so subsequent
source edits cannot change the already verified response. Unlisted, altered, linked, malformed
or busy evidence produces contextual refusal. HEAD is body-free; preview status is explicitly
private, never authenticated publication. Status now reports the missing protected runner
instead of a fixed quality score or a historical result as current work.

The existing pinned Vazirmatn font is local-only, accompanied by its copyright notice,
packaged data files and a distinct OFL SBOM entry. Native source and installed RECORD probes
verify bytes; fonttools 4.60.2 confirms the existing required Sorani codepoints and wght axis.
This is not browser shaping, accessibility, clean-install or performance acceptance. Native
Windows tests also reproduced differing lstat/fstat ctime semantics; stable identity uses
birthtime on Windows alongside full content hashing. Decoded large media exercised real disk
spooling. Broken-pipe, native directory junction/hardlink and same-site-origin refusals have
named regressions. Preparation/storage checks are bounded but do not certify kernel-blocked
I/O, OS ACL privacy or target playback throughput.

The exact full gate exited 1: 4,003 passed, three failed, three errors, one warning and zero
skipped in 1,047.02 seconds. Lint, strict typing and formatting passed across 264 files.
Canonical JUnit confirms 61 artifact, 44 billing, 23 submission, seven queue, 29 generation
and 38 upload cases passed. Failures: dirty-checkout wheel refusal; three dependent build
fixture errors; current-source VEX binding; and newly staged Vazirmatn-COPYRIGHT.txt absent
from HEAD's archive. That additional archive failure is an explicit release prerequisite,
not hidden by unstaging the notice or weakening the assertion. Test-first and intermediate
contract/attribution failures remain in the T4 logs. No harness, fixture or golden was edited.

Evidence: T4-read-test-evidence.json and gate-T4-read.log. Canonical JUnit SHA-256:
`cd3a2b515adc60d3e74e03453d5ef73735d7c4170bbc16ce568b4734e4a14285`.
Gate log SHA-256:
`cdd227ea07416bc6582338485755395ab06219e54c4992119532cb6c580a8936`.
Current source package SHA-256:
`510bfb7e333b7210cf6fd252cc26a7b22cb9ffd63b9d1b744f2527830ccac65a`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, source uncommitted.
Observed runtime: CPython 3.12.10, SQLite 3.49.1, DBOS 2.29.0, pytest 9.1.1,
ruff 0.9.6, mypy 1.15.0 and fonttools 4.60.2. Historical hardware inventory above is
not a new performance measurement. All launched gate/probe processes are terminal.

Serena now has 151 definition/reference records. Statistical acceptance research records
actual synthetic counterexamples: rating reordering changes the hook difference, duplicating
one reviewer inflates confidence, public seed/item order reconstructs blinded roles, and
unverified sign-off strings permit an 80% first-pass card to evaluate a 10/10 claim without
refusal. No comparison/scorecard source was changed; no real reviewer or benchmark was run.
These helpers require approved, versioned repair before any locked evaluation or verdict.

HTTP generation still refuses the missing protected worker. Legacy persisted job states,
frontend filename-only generation/quality/media assumptions and metadata-only edits remain
unaccepted. Private storage preflight, migration, producer checkpoints, authenticated review,
exact-byte export, current VEX, clean builds/CI and all human/sustained acceptance remain open.
No paid call, licence acceptance, commit, CI pass, browser/NVDA acceptance, publication or
ledger flip occurred. The seven-phase program remains active, not an accepted studio.

## T3 Historical Read Adoption Checkpoint

HTTP history now reads stable bounded persisted snapshots instead of treating JobManager's
cache as authoritative. Raw-record digests bind the sanitized projection; no original record
or media is rewritten. Legacy completed/review flags are unverified-historical; abandoned
queued/running work is interrupted pending explicit reconciliation, never auto-enqueued.
Reported failure/cancellation remains visible. Server paths, tokens/options, invented scores,
durations and work percentages are not exposed. Manifest-listed candidate IDs have unknown
measurements until independent preview validation. Malformed, linked, missing and partial
records expose diagnostics; a successful empty jobs list cannot conceal refused entries.
The old HTTP caption edit refuses revision_required without changing metadata/media/ASR.
It does not yet create the required immutable measured render revision.

Native probes cover real disk refresh, exact preservation, directory junctions/hardlinks,
budgeting invalid-record bytes, encoded portable IDs, malformed Unicode and actual HTTP.
Bounded native deep JSON previously raised uncaught RecursionError; all three shared write
routes now contextualize it without changing bounds/recursion limits. Accepted native sockets
now have a 60-second timeout, observed by the real HTTP test. This is not an entire zero-hang
reliability corpus, browser workflow or certified legacy writer replacement.

Exact full gate exited 1: 4,066 passed, three failed, three errors, one warning, zero skipped
in 1,039.58 seconds. Lint/types/format passed across 266 files. Canonical JUnit independently
confirms 63 history, 61 artifact, 44 billing, 23 submission, seven queue, 29 generation and
38 upload cases passed. Failures remain dirty-checkout wheel refusal, three dependent clean
build fixture errors, newly staged font notice absent from HEAD's archive and stale VEX binding.
No test, fixture, golden or enforcement policy was weakened. Test-first/intermediate native
JSON, contract, Unicode and timeout failures remain in preserved T3-history logs.

Evidence: T3-history-test-evidence.json and gate-T3-history.log. Canonical JUnit SHA-256:
`8ebc4425705c542049426c3c5a05be7fe59c57f7630800ab41b7e120b99beb25`.
Gate log SHA-256:
`b48a9938e0f62199f51024c113144487b427eea309e2f2b957d90ce4540cb1f9`.
Current package SHA-256:
`487857046ae88bbc7f8a929e92bd65d54cd389dd11550f3fe51f43f311eeaaa8`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, uncommitted source.
Runtime remains CPython 3.12.10, SQLite 3.49.1, DBOS 2.29.0, pytest 9.1.1,
ruff 0.9.6, mypy 1.15.0 and fonttools 4.60.2. Hardware inventory is historical,
not a new throughput/quality measurement. Gate/probe/server processes are terminal.

Serena now has 180 definition/reference records. Read-only native Windows ACL observations
refuse current work/jobs/uploads paths for foreign-principal allow ACEs and inherited DACLs.
No permissions changed and no third-party readability was tested. Private supervisor storage
must be created/verified before sensitive production writes, not asserted by a constructor.
protected-worker-research.md confirms absent QC selects private review under production
constraints; no profile downgrade or fabricated QC is necessary or authorized.

Fresh isolated in-app browser observation: 320 CSS pixels gives document scrollWidth 608;
the existing ready badge contradicts unavailable-worker status. Saved mobile content-region
capture was inspected; desktop capture was rejected for clipping/black remainder. Empty-input
click and subsequent dialog/close controls timed out; no verified empty-submit result or full
browser acceptance is claimed. No file was selected/submitted. The exact isolated server child
was verified and stopped without console cancellation. User dismissal was requested for the
stalled temporary audit tab. See history-ui-audit/notes.md for source/tool/provenance limits.

Protected worker/checkpoints, authoritative durable lifecycle, legacy programmatic daemon/
writer replacement, private storage/authentication, frontend adoption, real rendered revisions,
authenticated export and independent/sustained acceptance remain required. No paid call,
model inference, licence acceptance, release/CI approval, commit or ledger flip occurred.
Full seven-phase scope remains active; no accepted migration, verified candidate or 10/10.

## T5 Studio Adoption Checkpoint

The vanilla Sorani studio now adopts real-byte upload, source-ID identity, explicit bounded
history and guarded private-preview routes. Native labelled input replaces hidden/filename
lookup behavior. Upload identity and exact schema-1 submission intent persist before egress;
uncertain outcomes keep the same content/token and block competing work. Browser storage
errors refuse new work visibly. These mechanisms do not replace the protected durable worker.

The unavailable worker is not shown ready. History selection is explicit and persisted;
legacy completion stays unverified. Unknown quality/duration stays unknown; observed stages
are not invented work percentages. Candidate text is inert. Selection changes clear stale
media/measurements; measured private HEAD gates playback, and superseded checks are cancelled.
Private copy is not verified export. Revision/approval/export remain disabled because their
authenticated/rendered paths do not exist yet, rather than exposing metadata-only success.

Final package SHA-256:
`66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, uncommitted source. Serena mapping
now has 186 definition/reference records. Lint/types/format pass across 268 files; 47 focused
UI/web/robustness cases pass, including 14 new structural/declared-color cases. Node 24.15.0
checks actual extracted JavaScript syntax. Prettier 3.9.6 is one-off MIT formatting tooling,
not a project runtime/CI dependency. These are not full JavaScript execution regressions.

Fresh isolated native in-app browser checks verify two same-filename fixture uploads with
different source IDs and matching actual bytes, server/reload recovery, persisted settings,
explicit historical context, private seeking/download, damaged-sidecar refusal and Retry,
inline invalid-container refusal and no horizontal overflow at five widths from 320 to 1440.
Accepted inspected screenshots and detailed limits are in history-ui-audit/next-ui/notes.md.
The old stalled audit remains historical evidence; the new working session does not rewrite
it. The temporary audit tab was closed, viewport reset, and exact isolated server child stopped.

Bounded native focus/disclosure/select/checkbox checks are not full keyboard or NVDA acceptance.
Control+Equal had no zoom effect; 200% text resize and 400% zoom remain unverified. Current
screenshots cover fixture states, not actual generation/revision/review/export or a human
creator/editor study. Automated complete browser regressions, native copy review and full AA
remain open. OS-private storage/authentication, protected execution/billing, actual measured
revisions, authenticated exact-byte publication and independent/sustained acceptance remain
required. No paid call, model inference, licence acceptance, commit, CI pass or ledger flip.
The exact full gate's terminal evidence follows below.

## T5 Terminal Gate And Transport Fault

Exact full rerun exited 1: 4,080 passed, three failed, three setup errors, one warning and
zero skipped in 1,017.13 pytest seconds. Lint/strict types/format pass (268 files). Canonical
JUnit confirms all 14 new UI cases, 67 documentation claims, 63 history, 61 artifacts,
44 billing, 23 submissions, seven queue, 29 generation and 38 upload cases passed.
The remaining failures are dirty-checkout wheel refusal, dependent clean-build fixture errors,
staged font notice absent from HEAD's archive and stale current-source VEX. No harness/test/
golden/fixture policy was weakened; no ledger row was flipped or required CI claimed.

The first full run reported 4,078 passes, five failures and three errors: pytest collected
README/PROGRESS before their new module/WIP entries were added. Preserve both genuine failures
in T5-ui-first-test-evidence.json/T5-ui-first-junit.xml. Fresh complete claim suite (67 cases)
and the frozen-document full rerun resolve those two failures, not retrospectively erase them.

Final evidence: T5-ui-test-evidence.json, T5-ui-junit.xml, gate-T5-ui-final.log.
Canonical JUnit SHA-256:
`b1d396a96f0ba79f67e71ee0a327b7e90532e1ea9eeec7dace9a8a3760a60594`.
Gate log SHA-256:
`330748f35c84cbaf512274138ec82eccc590f00302078cb5d12b37bd1abf1b5d`.
Package remains `66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39`;
unchanged baseline HEAD, uncommitted source. All launched verification/audit children are terminal.

Additional actual browser transport fault: an isolated test-only handler drops the first PUT
acknowledgement after untouched receive commits/probes fixture bytes. UI remains unknown with
empty source and locked competing upload until guarded recovery; reload retains the same source.
Native disk/log checks find one reservation, one actual commit, two recovery reads and zero
repurpose requests. No fake pipeline/status or paid request. Native-upload-loss-evidence.json
and accepted screenshots 09/10 bind the bounded check; it is not an automated CI reliability pass.
Host inventory records HAWAPC01, Windows 11 Pro build 26200, Threadripper 3990X and physical RAM;
browser engine version is not exposed/claimed. No GPU/model or pipeline performance measurement.

Protected lifecycle/storage/authentication, actual measured render revisions and authenticated
review/reconciled export remain required. All independent quality/creator/editor/AA/NVDA/zoom,
clean installation/current VEX/CI and sustained acceptance obligations remain active. No accepted
candidate, migration, whole studio or 10/10, publication/spending/licence authority is inferred.

## T3 Private-Journal Terminal Checkpoint

2026-10-02. Mandatory owner-private billing storage is implemented under the approved parent
program/D-276. New studio_private.py binds actual root/database identity and validates real
components, ownership/access and SQLite sidecars. Unsafe existing state is refused without
byte/permission repair or discarded recovery evidence. Raw nonportable names are refused
before Windows normalization. SQLite opens/commits and every upstream request/result use the
binding; original reservation, occurrence, replay, uncertainty and canonical-model policy remain.

The exact Git Bash invocation of scripts/verify.sh exited 1: 4,112 passed, three failures,
three setup errors, one warning, zero skips in 1,076.93s. Lint/types/format pass across 270 files.
All 26 private-path, 50 billing, 23 outbox, seven queue, 38 upload, 29 generation, 61 artifact,
63 history, 14 UI and 67 claim cases pass in the fresh canonical report. Clean-build refusal/
dependent errors, staged font notice absent from HEAD archive and current-source VEX remain.
T3-private-journal-test-evidence.json derives group verdicts from actual canonical testcase
results; it is unaccepted engineering evidence, not authenticated production acceptance.

Canonical JUnit/snapshot SHA-256:
`f4c4d658e1bcb7937dc11367d2699527bb13ecb810dcd21a9ea95d3e49ebb0ee`.
Gate log SHA-256:
`5212b88f63a9ffac2b70518720ce389279179ccc8c6a642aa630083447ad1c1c`.
Package SHA-256:
`637e9acc148c7b9000605df4c2a4006abd7b5268b6e9617641f509e7a6b6c302`.
HEAD remains `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, uncommitted. Native host/runtime
inventory is T3-private-journal-host.json (CPython 3.12.10/SQLite 3.49.1/DBOS 2.29.0,
pytest 9.1.1/ruff 0.9.6/mypy 1.15.0); no reel speed/quality measurement is claimed.
The 30-file source/test/document manifest matched at terminal capture. PROGRESS's added
terminal evidence paragraph is a subsequent documentation update, not a changed module map
or retroactive gate input. Current post-update claim checks are separately recorded.

T3-private-journal-posix-final.json records 12 bounded native assertion observations using
existing Ubuntu CPython 3.12.0/SQLite 3.43.1. /tmp's filesystem reports ext2/ext3 and the same
canonical package_digest. Actual private modes/owner, shared-file/root/alias/hardlink refusal,
all unsafe/orphan sidecars, nonmutation and abrupt committed-WAL reopen are checked. No pytest/
runtime installation, model load, provider call or canonical Linux gate occurred. The earlier
raw Python-tree digest is explicitly not rebound to this canonical source.

Actual Serena definitions/references include 21 fresh final records plus the 210-record
research map. Private storage adoption still has a concrete exception-import cycle to resolve
before using the binding in SubmissionStore; private-storage-adoption-research.md records
startup/global caller impacts. All needed verification/Serena children are terminal. No ledger
row, CI, release, spending/trusted-root approval or completion is promoted. Persistent authorized
pool/store identity and restart reconciliation, whole-studio private storage/per-user HTTP auth,
protected producer/runtime/governance, revisions/review/export, statistics repair and every
frozen independent/sustained acceptance obligation remain active. The full goal stays active.

## Private Upload/Outbox Terminal Evidence

2026-10-03 local / 2026-10-02 UTC. Exact gate exits 1: 4,137 passed, three failed, three
setup errors, zero skips in 1,034.68s; lint/strict types/format pass for 272 files.
T3-storage-test-evidence.json derives all case/group counts from fresh canonical XML;
all 25 new storage and 378 earlier studio/claim cases pass. The actual terminal exit is
T3-storage-gate-exit.json. The 288-file frozen source/test/script/document set and bytes
match before recording; terminal source package is
`6bde42cba644a4510bbdb1bdd28596dba7cece5c328612c6dcbcb0e3d7f0b2cb`.
HEAD is still 372a16645d7a8558bc6cedcff34a9fbfa13f712f, uncommitted. No row or CI promoted.

Canonical/snapshot JUnit: `f2283327b87c0aaddf3371e8d7313ff53a21b8d286edd434340c350c20c7ad0f`.
Gate log: `77e3b55d8cad51e78746a7eb435670bb4763dbe0b886b08198d426741739bfda`.
Frozen manifest: `3806ea128fa581a3ac474f175bcaa9ccab0bb3511203961906bdf083c1514a19`.
Failures remain dirty wheel/dependent build fixtures, staged font notice absent from HEAD
archive and stale qualified VEX. Protected harness, references and qualification are not
weakened or rebound. Source/installed local font acceptance still needs clean committed CI.

T3-storage-host.json records actual Windows hardware/OS, CPython 3.12.10/SQLite 3.49.1,
DBOS 2.29.0/pytest 9.1.1/ruff 0.9.6/mypy 1.15.0, actual selected WinGet FFmpeg 8.1.1 and
its FFprobe/fixture SHA-256 values. It is not claimed to be the project's pinned production
installation. Real remux/first-frame positives cover seven suffixes; real wrong-container
and playlist inputs refuse. Native live-server fixtures exercise configured/default private
startup and real HTTP reservation/PUT/status, not browser or authenticated user acceptance.
The six-failure first storage run, real accepted-TS-under-MP4 counterexample and nine wrong
new test response-shape assertions remain preserved separately; none is relabelled a pass.

T3-storage-posix.json and T3-storage-posix-wal.json record seven new directory/metadata/outbox
and twelve repeated current-source journal/WAL observations in existing Ubuntu CPython
3.12.0/SQLite 3.43.1 on /tmp (reported ext2/ext3), same canonical package identity. No runtime
install, canonical Linux gate, production mount certificate or provider/model run occurred
in these probes. T3-storage-tool-runtime.json binds actual CPython 3.14.6/serena-agent
1.7.1.dev0 and symbol/reference implementation hashes. Fresh final maps contain 42 storage
and 17 acceptance records with retained import fallbacks and manually inspected child strings.

The old exception import/deserialization remains compatible; private uploads/outbox now
adopt actual directory/file/SQLite fences and owned staging cleanup. This is not all studio
storage, persisted authorized pool/root identity, authenticated HTTP sessions or an enabled
protected worker. Existing original uploads/jobs/media are preserved, not silently moved or
permission-repaired. Burned-in revisions, signed exact-byte review/export, runtime/governance/
billing adoption and all independent acceptance remain open. Current synthetic T8 diagnostics
still show false 10/10 admission; http-owner-boundary-research.md records why loopback and
cookies alone cannot establish local-user identity. Neither is a completed implementation
or a human benchmark. PROGRESS's terminal paragraph is post-gate documentation; separate
current claim checks bind that update without rewriting the frozen gate evidence.
