# Current-Source Security Review Packet

Prepared 2026-10-02. Status: engineering evidence, NOT a security approval.
Qualified-reviewer: pending. Owner release approval: pending.

## Identity And Observed Boundary

HEAD: `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, with uncommitted upload work.
Source package digest used for the readiness and scanner observations below:
`52d23b1833eb3d761b4a6781a60ac43bd66b2cdca1b45fa1fc05c273bbebc8f0`.
The final T1 gate is red; see `gate-T1-final.log` and `readiness.md`.
Subsequent malformed-upload hardening changed the source package to
`a3cf9e5e11d006e816cf8a98880043367d3d95dc978873221082b22b88521dbd`.
The copied receipt and scanner report remain evidence for the `52d23b...` snapshot only;
they are not readiness/security acceptance for the newer source.

Response-loss recovery subsequently changed the package digest to
`29031bcdf7ec18d980ee614b7801bc72c9535bf360c1b650f1c15ee8bf6e9ec0`.
No new source-bound WSL or accepted security receipt is implied by that engineering repair.

Checked-in `security/wsl-asr-vex.json` SHA-256:
`2171e25dd5bf65271673a7f08cbb2d6496a39ff482b80cbda93b317a730718e3`.
Its reviewed source digest is `81f6f606f89115ddedcba38941aad0b3f86cc59187a52b21b2a8a4f609bc5eba`;
review date 2026-08-09, expiry 2026-09-08. Neither its dates nor its digest were changed.
The policy is a parsed JSON document, not itself an authenticated reviewer signature.
Blocker #24 explicitly prohibits treating digest rebinding as re-review.

The first current-source live boundary check exited 1 before scanning or producing success
evidence: `sources/52d23b1833eb3d76/.ready` was missing. Ubuntu was running under WSL2.
A direct metadata-only inspection of the existing Ubuntu interpreter reported Python 3.12.0,
OmniASR 0.2.0, torch 2.8.0, transformers 4.57.6, fairseq2 0.6 and qwen-asr 0.0.6.
This narrower inventory is not a canonical receipt, a full dependency audit or inference.

The existing environment generation `Ubuntu-33853eeafb05ecf1b998dc84` was complete before
revalidation. Its `.complete.json` hash was
`ca32362d005d17bb308e547f525355125932a416d0a215abb852b0f62757d25c`.
All three canonical assets existed at the policy's expected sizes. Size alone is not integrity.
The prescribed readiness procedure subsequently exited 0, rehashing 43,546,500,168 asset bytes,
checking the 141-distribution locked inventory, importing the worker dependencies and seeing
two GPUs. It reused the complete environment (`HAWEDIT_WSL_ENV_REUSE=1`); no model inference
was run. The source-bound receipt is copied verbatim into `current-wsl-receipt.json`, SHA-256
`57ab593ceea33e027eb96e47dd4834d4a9e5100760a4f2b41fb9b14fde8d8825`.
Terminal log: `current-wsl-readiness.log`. This is readiness, not qualified security approval.

## Material Scope Gap: The Default Champion

`pipeline._build_and_run` resolves the champion adapter by default when OmniASR is requested
without an explicit stock-decoder choice (`pipeline.py:5362`). D-260 and the owner's
Champion Supremacy canon prohibit silently substituting the stock model.

`OmniAsrBackend._load` explicitly states that its adapted branch does not yet carry the
verify-to-load binding (`asr.py:403`). `_load_adapted_llm` obtains the base checkpoint through
fairseq2's asset store, reads the bundle tokenizer, constructs a model and calls
`PeftModel.from_pretrained` (`asr.py:500`). This is separate from the stock branch's held
verified descriptors. A stock-path regression cannot certify that adapted branch.

> [!WARNING] Contradiction
> The policy's unrestricted claim that verified descriptors remain held through model
> construction is not established for the default adapted route. A readiness procedure
> checking canonical assets and imports does not close that gap. Re-review must explicitly
> include the champion base, adapter, tokenizer, configuration, licence and loading path.
> Do not narrow the product to stock ASR merely to obtain a security pass.

`asr_worker.run_request` accepts `lora_adapter` and `validator_model_dir` from its file
protocol (`asr_worker.py:50`). The future studio must not expose arbitrary server model paths.
Determine which host configuration is trusted and bind approved model identities before load.
Request containment and declared segment duration checks do not themselves demonstrate a
complete hostile-media sandbox or a bound on actual decoded tensor dimensions.

## Twelve Dispositions To Reassess

These are checked-in policy statements, not newly accepted dispositions. Aliases remain in
the original JSON. Review the complete live scanner output, including any new findings.

| CVE | Current policy status | Required current-source review focus |
|---|---|---|
| 2025-3001 | affected | LSTM primitive reachability and constraints on decoded audio/tensors |
| 2025-3000 | affected | TorchScript/transitive execution; no user code or model repository dispatch |
| 2025-2999 | affected | Sequence unpacking, actual audio bounds and model-controlled tensor shapes |
| 2025-55551 | affected | LU/transitive linear algebra; bounded worker exposure is mitigation, not absence |
| 2025-55552 | not_affected | Rotation/random-like operations remain unreachable in the actual audio graph |
| 2025-55554 | affected | Audio values influencing nan conversion and integer tensors |
| 2026-4538 | not_affected | PT2 loading absent across stock, adapted and validator loader paths |
| 2026-24747 | affected | Held verified bytes for every checkpoint load, especially the default champion |
| 2026-4372 | affected | Recursive configuration guards before every owned/transitive Transformers load |
| 2026-1839 | not_affected | Trainer RNG restore absent; exact runtime version constraints |
| 2026-5241 | not_affected | Nested LightGlue/trust-remote dispatch remains outside the model allowlist |
| 2025-14929 | not_affected | X-CLIP conversion absent from the deployed worker and loader graph |

The upstream PyTorch advisory still lists <=2.9.1 as affected and >=2.10.0 as patched.
Therefore the observed 2.8.0 cannot be described as patched; identity checks are application
controls, not a library fix. [PyTorch advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p).
The existing Transformers disposition cites an upstream security change, which was inspected,
but this packet does not establish that its fix is present in the pinned 4.57.6 runtime.
[Upstream change](https://github.com/huggingface/transformers/commit/a7f8e7ff37d87d1a1a0c8cf607971c607741452f).
Sources inspected 2026-10-02. Changing the model/runtime lock requires development evidence
and an ADR, not an opportunistic package upgrade.

## Existing Evidence And Its Limits

- `test_omni_loader_reads_only_held_verified_descriptors`,
  `test_omni_assets_are_hashed_before_the_pipeline_module_is_imported`: stock loader contract;
  inspect their test doubles before attributing any full-model execution to them.
- `test_hardlinked_asset_is_refused_before_hash_or_load`,
  `test_effective_card_cannot_disable_restricted_checkpoint_loading`: asset/card controls,
  not adapted-loader proof.
- `test_qwen_validator_refuses_a_code_loading_config_before_imports`,
  `test_config_cannot_override_trust_remote_code_in_a_nested_model`: owned validator guards,
  not a universal proof of every transitive third-party loader.
- `test_missing_current_receipt_fails_before_tools_or_evidence`,
  `test_post_audit_receipt_drift_cannot_publish_evidence`: fail-closed gate behavior.
- `tests/test_vex.py::_evaluate_fixture` evaluates generated fixture findings at the fixed
  date 2026-08-09. It is not today's live scan. A genuine later review will require deliberate
  harness maintenance under the self-edit-marker rules; never falsify dates to fit the fixture.
- `.github/workflows/gate.yml` runs the self-hosted WSL job only on a main-branch push.
  A skipped PR job is not current runtime/security evidence. Runner registration remains #25.

## Current Live Refusal: Six Additional Findings

After current-source readiness passed, the prescribed live gate exited 1. It refused the
expired policy, the reviewed/current source mismatch and these six unmatched findings:

| Installed package | CVE / GHSA / PySEC alias | Review state |
|---|---|---|
| accelerate 1.12.0 | CVE-2026-69112 / GHSA-4J2P-28Q2-5M79 / PYSEC-2026-3804 | untriaged |
| transformers 4.57.6 | CVE-2026-80047 / GHSA-X9R9-C232-4Q39 / PYSEC-2026-4174 | untriaged |
| transformers 4.57.6 | CVE-2026-9856 / GHSA-XRQW-3RRV-VX5W / PYSEC-2026-3929 | untriaged |
| urllib3 2.7.0 | CVE-2026-97687 / GHSA-8988-9CW3-XX77 / PYSEC-2026-4175 | untriaged |
| urllib3 2.7.0 | CVE-2026-97688 / GHSA-GH4C-6FX4-QH6G / PYSEC-2026-4176 | untriaged |
| urllib3 2.7.0 | CVE-2026-97689 / GHSA-VXQ7-64XX-V4GW / PYSEC-2026-4177 | untriaged |

The terminal refusal is preserved in `current-live-vex.log`. The requested accepted-evidence
file was not produced. A finding is not a demonstrated HawEdit exploit or an accepted
disposition; a current review must assess these in addition to the twelve old dispositions.
Do not assume the original policy's package applicability covers accelerate or urllib3.

A subsequent diagnostic scan reused the existing hash-locked scanner helper and captured its
raw bytes as `wsl-pip-audit-current-2026-10-02.json`. It reported 141 audited packages and
18 normalized findings; the raw report has 27 vulnerability rows because some database
records repeat. Count identities after validated alias normalization, not raw repeated rows.
Report SHA-256: `c70c97e816a2ce2e85ab79d1d2ea03147739af609d7cad1e3440a6819250bed8`.
`wsl-scan-current-2026-10-02.json` records the exact source, receipt, scanner identity and UTC
observation. Its status is `unreviewed-diagnostic-scan`, not accepted gate evidence. Scanner:
pip-audit 2.10.1, uv 0.11.15, WSL Python 3.12.0, the hardware recorded in `readiness.md`.

The upstream urllib3 notices describe separate HTTPS-proxy TLS configuration errors,
chunked-deflate infinite looping and an unbounded chunk-size line. Review all networking
paths, proxy configuration and bounded reads without recording secret proxy URLs or tokens.
[Proxy TLS](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77),
[Deflate loop](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g),
[Chunk header](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw).
The initially attempted project-specific Accelerate/Transformers advisory URLs were unavailable.
Follow-up located the upstream checkpoint-path proposals and Transformers fixes. These are
review starting points, not proof that the pinned runtime contains a fix or cannot reach the
vulnerable operation:

- Accelerate: inspect sharded `weight_map` containment, symlink/special-file behavior and
  transitive dispatch. [Upstream proposal](https://github.com/huggingface/accelerate/pull/4070),
  [Follow-up](https://github.com/huggingface/accelerate/pull/4138).
- Transformers custom generation: code can be downloaded before trust consent; disabling
  execution alone is not a proof of no file write. Inspect local/offline model resolution
  and every transitive generation call.
  [Upstream fix](https://github.com/huggingface/transformers/commit/cbc1651a032b923da7f4b44b3d0e6f68e6ba6b55).
- Transformers chat templates: inspect tokenizer/processor `save_pretrained` and named
  template paths. Repository search found no owned call to `save_pretrained`,
  `load_checkpoint_in_model`, `load_checkpoint_and_dispatch` or `custom_generate`; it did
  find visual `apply_chat_template` calls. Neither result proves transitive unreachability.
  [Upstream fix](https://github.com/huggingface/transformers/commit/eaaaf8494dd5386634ae37d1d122212fdc315be5).

## Review Handoff

The reviewer must inspect the exact source snapshot, complete dependency/scanner identities,
canonical and champion assets, model-loading paths, uploaded-media parser exposure, and all
findings/aliases. Record justified dispositions, limitations and accepted residual risks.
Bind reviewer identity and sign-off to source, locks, assets, policy and live report hashes;
the existing parsed date strings do not authenticate a reviewer.

Only after a genuine review may the policy be updated. Run the existing live gate against
that exact source and preserve its non-overwriting accepted evidence. Require the exact
repository gate and applicable exact-SHA CI; no row is accepted from this packet alone.
No paid service, transcript transfer, model inference, licence acceptance or publication
was authorized by preparing this evidence.

## Changed Studio Boundary Snapshot

The T2 request/projection unit changes the current package digest to
`122ca64f6b9665951b353e2ea9f3fd8a2355be0bfb354b200ef82bd662c0b41c` at unchanged baseline
HEAD plus uncommitted edits. Source-ID validation now replaces raw web server-path submission;
actual generation remains refused until durable runner/governance configuration exists. Review
the new upload/request parsing and manifest/measurement projections in this exact snapshot.
Historical WSL receipts/scans do not authenticate this changed source. No policy dates or
reviewed digest were rewritten. Current gate and independent security acceptance remain open.

Serena's production caller research also found that recovery helpers are not yet connected to
Gemini's billed transport. Coarse DBOS replay cannot be represented as exactly-once external
billing. `durable-studio-research.md` records required pre-request intent, uncertain-result
reconciliation and trusted spending controls before enabling the studio worker.

A real local read-only check confirmed legacy unknown-route filesystem serving:
`GET /README.md` returned HTTP 200 / 62,095 bytes (`legacy-static-fallback-observation.log`).
The handler's final SimpleHTTPRequestHandler fallback is still present. No secret was read,
no new exploit or external exposure is claimed, and the temporary server stopped. Treat
removing that fallback and whitelisting UI/manifest artifacts as a release-blocking trust
boundary repair, not merely visual polish. T4's tests must cover unlisted ordinary files.

## T3 Mechanism Snapshot For Review

Current package digest is now
`830f77b699f6d38af61bf7c14e323b66751909d9a1fbcf0052a039a6152b8b28`, at unchanged
baseline HEAD plus uncommitted edits. Review `studio_submissions.py` and `studio_queue.py`
alongside the earlier upload/request boundary. SQLite stores immutable bounded snapshots,
client-token conflicts and dispatch acknowledgements. DBOS receives only the job ID, not
credentials or producer argv. Queue identity/limits are validated against actual persisted
DBOS state. A runtime-binding digest and decorator metadata are inputs, not certified
readiness or proof that the callback has protected billing and model-loading controls.

Actual mechanism tests include interrupted enqueue/acknowledgement and two-process recovery,
not interruption inside paid work. The exact full gate remains red: 3,899 passed, two
failures and three errors; the current VEX/source mismatch is one failure. The historical
readiness receipt, live scan and expired policy were not rewritten and do not authenticate
this snapshot. `T3-outbox-test-evidence.json` records canonical report/log hashes and all
30 new cases passing; it explicitly rejects acceptance inference.

`protected-worker-research.md` identifies the next boundary: pre-request durable billing
intent, trusted route/model/price/spending policy, bounded output/thinking reservation and
response evidence before replay. Current input-only estimates cannot certify a total spend
cap. No paid request or price policy was authorized or enabled. HTTP generation remains
unavailable until the protected producer worker is integrated. Legacy static fallback,
unverified status/read surfaces, champion loading, current qualified VEX review and trusted
reviewer verification remain release-blocking gaps. This packet grants no publication,
licence, spending, security or release approval.

## T3 Billing Mechanism Snapshot

Current uncommitted source package digest is
`69528dccd42f592175a3d09c41debcd072673e5d0c9dca71bff62a7e49fcc3a4` at unchanged baseline
HEAD. Review studio_billing.py, test_studio_billing.py and the optional shared-builder judge
transport hook. Intent/reservation precedes generation; only bounded usage-checked responses
are confirmed for deterministic replay. Repeated identical K requests retain separate indices.
Uncertain intents block further billed generation for the job and are never automatically
refunded. The local tests do not authenticate policy, provider reconciliation or actual bills.

Before production adoption, verify the signed policy/trust root, dated actual route/model/price
and token-cap semantics, conservative prompt overhead, live worker/model readiness, governance,
private storage permissions and HTTP isolation. The new journal holds private model output;
its constructor does not itself enforce OS ACLs. Optional Flash/Jev screeners use independent
transports and bypass judge_transport, including a separate Developer API route. Either govern
and journal each authorized route or visibly refuse it; do not enable confidential Vertex work
with an ungoverned screener. Existing boolean reconciliation helpers cannot clear these intents.

The exact gate remains red: 3,943 passed, two failed and three errors; canonical JUnit confirms
all 44 new billing cases passed without skips. T3-billing-test-evidence.json binds report/log
hashes, source and runtime versions. Clean-build prerequisites, current-source VEX, actual
qualified review, protected worker integration and legacy static/read repairs remain open.
Historical receipts/policy were not rewritten. No paid call or publication was enabled.

## T4 Read Boundary Snapshot

Current uncommitted source package digest is
`510bfb7e333b7210cf6fd252cc26a7b22cb9ffd63b9d1b744f2527830ccac65a` at unchanged baseline
HEAD. The earlier generic filesystem fallback observation is historical: this unit removes
that fallback and recursive media lookup. Review web.py/studio_artifacts.py and the native
GET/HEAD, origin, junction/hardlink, changed-evidence and real decoded-media regressions.
Requests receive only explicit UI/API/font or manifest-listed private preview routes.
Verified snapshots bind response bytes to measured digest/size/duration; they do not verify
reviewer authority, source semantics, publication policy or the measurement's authenticity.
Loopback/origin controls are not per-OS-user authentication. OS ACL enforcement remains open.

Offline Vazirmatn distribution adds fixed data-file inventory, a copyright notice and its
own OFL SBOM entry without changing canonical model policy. Source/installed RECORD checks
do not substitute for the required committed clean build. The notice is deliberately staged;
HEAD's archive cannot yet contain it. The exact gate has 4,003 passes, three failures and
three setup errors, zero skips. T4-read-test-evidence.json binds the canonical report/log.
Do not silently rebind VEX or unstage the notice to hide that additional archive failure.

Legacy history/UI, authenticated policy/trust roots, protected worker/governance/billing,
revision/export authority and independent acceptance remain release-blocking. The native
synthetic counterexamples in statistical-acceptance-research.md also invalidate reliance on
historical scorecard/comparison helpers for 10/10 or authenticated review; supplying booleans
or sign-off strings is not evidence. No paid request, promotion or publication was enabled.

## T3 Historical Read Adoption Under Verification

Current package digest is
`487857046ae88bbc7f8a929e92bd65d54cd389dd11550f3fe51f43f311eeaaa8`, still uncommitted at
baseline HEAD. Review studio_history.py, shared stable job/report records and HTTP cutover.
Original historical files/media are preserved; raw record digests bind the sanitized view.
Old completion/review flags stay unverified, abandoned work requires reconciliation, and
malformed/unavailable/partial scans are diagnosed rather than represented as complete history.
HTTP caption edits refuse without a measured immutable revision; no metadata-only success.
Native protocol tests cover refresh/origin guards and actual socket timeout configuration.
Unpaired Unicode and native deep JSON have contextual refusals. Legacy programmatic writer/
daemon execution, protected lifecycle, actual revisions and browser acceptance remain open.

Read-only storage-permission-details.json confirms current work/jobs/uploads paths fail the
existing private Windows policy for foreign-principal allow ACEs and inherited DACLs.
No ACL was changed and no third-party access was tested. Production must create/verify
private storage before sensitive writes and authenticate owner configuration/trust roots.
Neither a filename-bound history view nor loopback routing supplies that security authority.
Historical WSL receipts/scans and VEX remain stale for this source; no digest was rebound.

## T3 Historical Read Terminal Gate

The exact gate completed on 2026-10-02 with exit 1: 4,066 passed, three failures,
three setup errors and zero skips in 1,039.58 pytest seconds. Lint, strict type checking
and formatting passed across 266 files. All 63 new history/input regressions and all six
earlier studio test groups passed. T3-history-test-evidence.json binds the canonical
JUnit and gate log to the source digest above; this is unaccepted engineering evidence.
Dirty-checkout build refusal, the staged font notice absent from HEAD's archive and the
stale current-source VEX binding remain unresolved. No ledger row was flipped or CI
pass claimed. The verification and isolated audit-server processes are terminal.

Fresh browser observations are limited to an empty-state DOM and a partial mobile
content-region capture. Desktop screenshots were rejected, and the empty-input Generate
click stalled browser controls before its outcome could be verified. See
history-ui-audit/notes.md. This is not full-flow, keyboard, NVDA or AA acceptance.

## T5 Studio Adoption Under Verification

Current uncommitted source package is
`66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39`, at unchanged baseline
HEAD. Review studio_ui.py, compatible web.py dashboard re-export and structural contract
tests. Visible native File bytes use the validated upload API, not a path lookup. Opaque
upload/source identities and exact token/content/options persist before egress. Uncertain
outcomes lock competing requests; corrupt/unavailable browser persistence is a visible
refusal, not successful empty state. Full cross-tab/JavaScript fault execution remains open.

History uses explicit sanitized selection; textContent prevents candidate HTML injection.
Media URLs are job/clip-scoped, not metadata-supplied. Private HEAD checks response type,
digest validator and private marker; epochs/abort and media clearing prevent stale selection
from retaining a player/download/measurement. Stale test-sidecar refusal/recovery and actual
private download hashes were observed. These checks do not authenticate reviewer authority,
source fidelity, signed measurement provenance or a deliverable. Revision/approval/export
and generation remain visibly unavailable; no paid route or publication is enabled.

Native fixture uploads and inspected five-width screenshots do not certify OS-private
storage, per-user HTTP authentication, full AA/NVDA/zoom or real creator-workflow acceptance.
Existing native ACL refusals still apply; do not submit confidential production media to
current storage merely because the file picker works. The exact gate remains under
verification, and historical VEX/WSL receipts are not rebound. See
history-ui-audit/next-ui/notes.md for bounded browser proof and explicit remaining gaps.

## T5 Terminal Security Checkpoint

Exact frozen-document full rerun exited 1: 4,080 passed, three failures, three setup errors,
zero skips in 1,017.13s; lint/strict types/format passed (268 files). All eight studio groups
and fresh documentation claims passed. T5-ui-test-evidence.json binds canonical report/log
and versions to unchanged uncommitted package `66a377da...`. First-run module-documentation
failures remain in their original report; they are resolved by the fresh run, not hidden.
Clean-build, staged font absent from HEAD's archive and current qualified VEX remain open.

Actual isolated HTTP acknowledgement-loss evidence confirms the UI never treats uncertain
transfer as a validated source or retries bytes automatically. Guarded recovery and reload
retain the one actual committed source; native hash/log checks agree. The test-only override
changes socket response transport after real receive, not source/storage/pipeline truth.
Audit children are stopped and temporary tabs closed. This bounded fixture exercise does
not fix private ACLs, per-user HTTP authentication, cross-tab concurrency, signed policy,
protected worker/governance/billing, authenticated revisions/review/export or full acceptance.
No ledger flip, CI pass, trusted-root promotion, paid call or publication was authorized.

## T3 Mandatory Private Billing Journal

Current uncommitted package:
`637e9acc148c7b9000605df4c2a4006abd7b5268b6e9617641f509e7a6b6c302`, unchanged baseline
HEAD. Review studio_private.py and its mandatory studio_billing adoption, preserved original
billing assertions and new native root/file/sidecar/drift/crash tests. The measured prior
constructor accepted a shared root despite native private-policy refusal; the test-first
failures and subsequent fixes are preserved, not presented as initial correctness.

Existing Windows helpers create/check the private root/files; POSIX requires owner/private
modes. Refuse unsafe existing bytes/access, aliases, hardlinks, orphan journals and observed
root/database replacement. Fence SQLite and all three upstream paths. Confirmed absent
ephemeral sidecars may disappear naturally; recheck bound main/root rather than recreate them.
The real retained-WAL and original abrupt response-loss tests preserve uncertainty/recovery.

Exact full gate is terminal/red: 4,112 passed, three failed, three setup errors, zero skips
in 1,076.93s; 270 lint/type/format files pass. All 76 billing/private cases and every earlier
studio group pass. T3-private-journal-test-evidence.json binds canonical XML/log, frozen
source/test/document hashes, native versions/host and separately scoped POSIX probe. It
does not replace qualified current VEX, clean build or exact committed-SHA CI.

Journal-only lifetime identity binding is not persistent supervisor pool/root authority,
HTTP identity, private uploads/jobs/DBOS/trust/session storage, certified remote/DrvFS locks,
privileged-owner isolation or provider access/cap/invoice proof. A restarted supervisor must
reconcile authorized original storage before adopting/creating state for an existing pool.
Do not rebind old WSL/VEX receipts, promote test keys/policy digests, submit confidential
media to old shared storage, or enable a producer from these mechanism checks. Genuine
signed authorization, runtime/governance, authenticated measured revisions/review/export
and all independent acceptance remain required. No protected enforcement/fixture/golden
was edited or weakened; no row, release, paid call or 10/10 is authorized.

## Private Upload/Outbox Adoption, Still Unaccepted

2026-10-03 local. Current uncommitted package:
`6bde42cba644a4510bbdb1bdd28596dba7cece5c328612c6dcbcb0e3d7f0b2cb`;
HEAD remains 372a16645d7a8558bc6cedcff34a9fbfa13f712f. T3-storage-test-evidence.json
records exact terminal/red gate: 4,137 passed, three failed, three setup errors, zero skips
in 1,034.68s, 272 lint/type/format files pass. All 25 new storage and all earlier studio/
claim groups pass; all 288 frozen source/test/script/document files match at capture.
Clean build, missing-HEAD font provenance and qualified current VEX/CI remain unresolved.

Mandatory private bindings now cover UploadStore and SubmissionStore as well as billed
journals. Metadata uses owner-private exclusive/fsynced staging, checked atomic replace
and identity-bound cleanup; generic atomic_fs behavior is unchanged. Unsafe old state is
preserved/refused, not chmod-repaired. The native test-first junction case reproduced
deletion of unrelated test-only originals by old cleanup; the fixed full-gate case preserves
them and refuses a source. Lost outbox main state refuses without recreating empty SQLite.
The shared error's old import/pickle qualification stays compatible through explicit export.

Default/overridden server startup creates private upload leaves; import no longer initializes
public upload state. Real HTTP fixtures and seven real remux/decode positives pass; suffix-
specific probing refuses actual mismatched MPEG-TS/MP4 and the tested external HLS playlist.
The playlist was already refused before repair and is not a newly proven external-read leak.
Native FFmpeg 8.1.1 and actual fixture/executable hashes are recorded; no media sandbox,
project-pinned production install, owner-isolated privileged account or complete race proof.
Fresh current-source Linux observations on /tmp are not production filesystem certification.

Persisted supervisor authority, private jobs/events/checkpoints/DBOS/trust/session adoption,
authenticated local-user HTTP and true protected producer/runtime/governance/billing remain
required. http-owner-boundary-research.md identifies cross-port cookie scope and authenticated
media transport as design prerequisites; no session scheme is certified by that research.
T8-current-scorecard-counterexample.json still reproduces unsupported 10/10 admission from
synthetic malformed/unsigned input, not an accepted verdict. Repair evidence authorization,
statistics/blinding/QC escalation before evaluation. Preserve every independent/sustained
threshold, genuine owner/editor signatures and current qualified source review; test flags,
test keys or old receipts cannot grant authority. No new spending, licence, release or row
completion is authorized by this unit.
