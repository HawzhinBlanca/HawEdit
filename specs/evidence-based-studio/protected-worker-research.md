# Protected Producer Worker Research

2026-10-02, HEAD `372a16645d7a8558bc6cedcff34a9fbfa13f712f` plus uncommitted source package
`830f77b699f6d38af61bf7c14e323b66751909d9a1fbcf0052a039a6152b8b28`. Research only;
no model inference, provider request, spending approval or changed canonical model policy.

## Shared Construction Boundary

`pipeline._build_and_run(args, on_event=discard)` is still the sole producer builder and is
exported as build_and_run. GeminiJudge/VertexGeminiJudge already accept a transport callback.
Their construction in the shared builder does not currently expose a studio-specific transport
guard. A narrow optional trusted transport parameter is a candidate integration, preserving
existing CLI/durable callers and routing both Path A discovery and editorial judging through
the same guarded client. Do not rebuild a separate studio producer graph or use process-global
stderr/client mutation to inject it. Record the exact interface in the implementation ADR/plan
before source edits and test every existing caller family.

Five additional Serena definition/reference records bring the map to 86. count_parts feeds
PathADiscovery._discover_single and token/HTTP/governance/key tests. judge_with_count feeds
judge and authoritative-count/owner-token-ceiling tests. build_visual_composer feeds the shared
builder and device-assignment tests. Constructor method references are empty in LSP, so class
references and direct constructor call sites must also be mapped before changing them. Existing
ASR factory mapping remains applicable; it is unchanged in this submission unit.

## Cost Evidence Is Not A Hard Spending Cap

Source inspection: judge.estimate_cost_usd uses provider-counted input tokens multiplied by
the frozen BLUEPRINT-derived USD_PER_MILLION_TOKENS=2.0. BilledCall stores that estimate.
Gemini's inspected generation payloads have schema/temperature but no maxOutputTokens.
They do not use output/thinking usage to compute an account bill. Do not turn these estimates
into a maximum-charge guarantee or silently change the frozen specification's cost table.

The current Developer API table separately prices Gemini 2.5 Pro input/output, including
thinking: standard prompts <=200k have USD 1.25/10 per million, above that USD 2.50/15.
This is public Developer API pricing, not the user's actual bill, Vertex contract or approval.
[Official pricing, retrieved 2026-10-02](https://ai.google.dev/gemini-api/docs/pricing).
The API exposes maxOutputTokens and says its omitted default is model-dependent.
[GenerationConfig reference](https://ai.google.dev/api/generate-content).

The protected worker therefore needs an owner-authorized, dated route/model/price/cap policy,
provider-counted input plus conservative bounded output/thinking reservations, and durable
atomic allocation before transport. Preserve the actual submitted cap in request identity.
Confirmed usage may adjust a reservation only through validated bound response evidence;
unknown outcomes retain their reservation and require attributed provider reconciliation.
Refuse unsupported pricing/routes/tools instead of assuming an unpriced call is free. Any
output cap/tuning needs development evidence before frozen holdout evaluation. No cap is
chosen or paid work authorized by this research.

## Durable Paid Intent

The registered worker receives only job ID, resolves its immutable outbox snapshot and
revalidates source, effective configuration, source/runtime/model identities, readiness and
trusted governance before model/hosted work. A digest or checkbox is not proof of those facts.
Persist an intent/request digest before generateContent; preserve confirmed bounded responses
as immutable private evidence before continuing. A crash/network error without response
evidence means interrupted/uncertain, not a blind replay. Count/discovery/judgment must bind
the same content and governed route; credentials/headers remain out of saved JSON/DBOS input.

The new queue's confirmation means only a matching DBOS execution exists. Its probe tests
do not prove model-step recovery, billing exactly once, legacy migration, cancellation of a
synchronous call, review/export or creator acceptance. Existing recovery checkpoints may help
reuse completed artifacts but cannot substitute for missing pre-request billing intent.
Default champion verified-descriptor loading, current VEX, trusted reviewers and owner resource
packet remain open. Check selected runtime/device capability, not merely GPU inventory.

Next implementation: protected transport journal/budget controls and shared builder injection,
actual runtime/governance refusal and worker adoption, attempt-scoped events/checkpoints, then
truthful job reads/non-destructive migration. Keep HTTP unavailable until those controls exist.
Required tests include real response-loss/intent-write failure and re-entry reuse/refusal, shared
producer parity, source/runtime mutation refusal, actual configured budget ceiling and visible
legacy diagnostics. Independent editorial/performance/30-day acceptance remains separate.

## Implemented-Unit Design Before Source Edits

2026-10-02 continuation: actual Serena class/transport/error maps now total 92 records.
The narrow builder extension is optional keyword-only judge_transport, forwarded to both
existing constructors. It does not authorize or configure a second producer graph.

The journal policy is a trusted-supervisor input, not a web payload or authenticated approval.
It binds authorization digest, exact route/model, expiry, input/output/thinking bounds, integer
price upper bounds and a shared reservation pool. Keep policy immutable for its authorization
ID; a digest alone grants no authority. Atomic pre-egress reservations never automatically
refund; an uncertain intent blocks billed work for the job until attributed reconciliation.
Only bounded confirmed responses with valid usage and matching hashes may replay. Retain
separate occurrence indices for repeated identical content, preserving Path A's actual K calls.
Deterministic replay ordering still requires immutable source/configuration/checkpoint preflight.

Count the full bounded generation configuration, not merely prompt contents. Developer API
accepts generateContentRequest; Vertex accepts generationConfig beside contents. These shapes
are grounded in the official references, retrieved 2026-10-02:
[Developer token counting](https://ai.google.dev/api/tokens),
[Vertex token counting](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.publishers.models/countTokens).
Response usage separately reports prompt, candidates and thoughts; maxOutputTokens alone must
not be represented as proof of total invoice. Conservatively reserve output plus the configured
upper bound for billed thoughts; validate returned usage without releasing the reservation.
[Generation/usage reference](https://ai.google.dev/api/generate-content).

The current canonical-model page reports a 65,536 output limit and restricts 2.5 access for
new projects. This is an additional readiness condition, not permission to switch models.
[Gemini 2.5 Pro, retrieved 2026-10-02](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro).
No provider access, semantic output/thinking-cap guarantee, account price or governance setting
is inferred from public documentation. A protected worker must verify those live prerequisites
and authenticated owner policy before production adoption. Local protocol probes test mechanism,
not real Gemini responses, account cost, editorial quality or spending authorization.

## Preflight Adoption Research After The Mechanism Unit

Current uncommitted source package is
`69528dccd42f592175a3d09c41debcd072673e5d0c9dca71bff62a7e49fcc3a4` at unchanged baseline
HEAD. The journal/shared-builder unit does not enable HTTP production. Serena now has 116
records, including actual signature, file-binding, Vertex environment and WSL runtime helpers.
One lookup for a nonexistent _worker method failed without source edits; the corrected map
uses the inspected WslOmniAsrProducer._runtime definition. Both research logs are retained.

Existing vertex_acceptance._verify_signature snapshots bounded signers/signature files,
verifies exact document bytes with OpenSSH and records the unique signing-key fingerprint.
It hardcodes its one-shot acceptance namespace. A studio pool policy needs its own purpose
namespace and configured trusted principal/root, not a reinterpretation of one-shot approval.
Reuse the actual verification conventions through a narrowly reviewed shared hook; do not
trust a web-provided allowed-signers path, supplied approval digest or boolean confirmation.
Bind current package/runtime/model identities, route, material governance, prices/cap semantics,
pool and expiry to exact signed bytes. Preserve secret keys/tokens outside SQLite/DBOS inputs.

The live Vertex environment probe verifies ADC project/principal, billing and API enablement
without transcript content. It is not retention-policy confirmation or canonical model access.
Do not invoke it before owner-authorized preflight. WSL receipt loading checks current source
and actual interpreter/package identities; probe_wsl_runtime also rehashes live assets and
checks CUDA. Historical receipts cannot be rebound by editing their digest. The ASR bridge
chooses only the transcription runtime; build_visual_composer and device checks stay in the
calling process. Windows torch 2.13.0+cpu plus available physical GPUs is therefore not a
complete studio worker runtime. Select and validate one actual producer-capable runtime,
and keep SQLite/DBOS ownership on a supported filesystem/OS; do not assume cross-OS locks.

Further billing prerequisite: provider count/usage semantics need real authorized verification.
The official counting example itself shows a count of ten and prompt usage of eleven. Current
strict response matching deliberately refuses usage outside its reservation; it is not evidence
that a normal live response will match. The next budget-policy integration must conservatively
allow verified prompt overhead and thinking bounds without weakening arithmetic, refunding
uncertainty or claiming an invoice/account-wide guarantee from request caps. Pricing, quota,
retention and model availability are independently verified facts, not public-doc inferences.
[Counting/usage example](https://ai.google.dev/api/tokens).

Journal responses contain private model output. The protected supervisor must create/verify
private storage and the studio must remove legacy filesystem fallback before any production
adoption; merely calling a database private does not provide ACL or HTTP isolation. Existing
boolean external-reconciliation helpers do not authenticate provider evidence and must not
clear these intents. Complete protected policy/runtime/billing integration, scoped read/artifact
boundaries and non-destructive migration before enabling genuine studio jobs. No current
security, paid-call, creator, browser, benchmark or sustained acceptance is inferred here.

Additional adoption blocker: public generation options include screener selection, and the
shared builder constructs GeminiFlashScreener/JevScreener with their own transports. Neither
uses judge_transport. Guarding the canonical judge/discovery client therefore does not guard
all priced egress. GeminiFlashScreener also selects the Developer API independently of Vertex
governance. Before worker enablement, require an explicitly authorized screener route with
equivalent durable intent, budget and confidentiality controls, or refuse that capability.
Do not silently change the effective preset. Map these symbols/callers with Serena before
editing them; this observation is static research, not a tested screener repair.

## Native Storage Preflight And Review Defaults

During the next frozen-source gate, read-only CPython 3.12.10/Windows API probes evaluated
work, work/jobs and work/uploads with the existing assert_private_windows_path policy.
storage-permission-observation.json and storage-permission-details.json bind current package
digest `487857046ae88bbc7f8a929e92bd65d54cd389dd11550f3fe51f43f311eeaaa8` and UTC times.
All three paths refused with require_protected=False because an allow ACE names a principal
outside current user/SYSTEM/Administrators; require_protected=True additionally refuses
inherited DACLs. No permission was changed, no private input was opened, and no other-user
access was attempted. This is an actual policy refusal, not proof of third-party readability.

Protected adoption must use native owner-private storage creation/verification before writing
uploads, DBOS/submission/billing journals, model output or signature snapshots. Reuse the
existing Windows security helpers and POSIX owner/mode checks; do not call an inherited
workspace directory private or silently narrow/move historical owner files. Preserve original
historical data and diagnose incompatible storage. Check both the configured root and files,
including identity/link substitution. Loopback/origin guards are not per-OS-user authentication.
Signed policies and reviewer roots need configured authority and purpose namespaces, not
browser-provided paths or generated test keys promoted into production trust.

Source inspection also confirms production preview does not require a profile downgrade:
run_pipeline makes production assembly explicit internally; absent human QC selects private
review rendering, and _run_episode_delivery records pending-review outcomes. Preserve those
constraints through the shared builder. A future worker must never supply fabricated QC to
make generation succeed, interpret an episode manifest as authenticated completion, or let
the old metadata-edit API approve burned-in changes. These are inspected contracts, not a
new model run or proof that every producer can run on the currently selected runtime.
