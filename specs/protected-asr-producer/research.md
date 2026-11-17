# Protected Canonical ASR Producer Research

2026-10-14; baseline94d947832b790610b6c36904a2d247247cfabffa plus explicitly
recorded RT2B controller WIP. No inference/full-pipeline/reel pass is claimed.
Canon Model Lock: champion OmniASR only; existing validator is not replacement ASR.
Source ZAR38 SHA256bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2,
2313.8s/640x360/25fps. Fresh actual intake and complete original/proxy decode pass;
technical landscape encode is not an editorial candidate.

## Grounded Findings

- Actual Serena13pair current map includes WslOmniAsrProducer/transcribe,
  asr_worker/run_request, Snapshot/registry/broker/View in
  C:/Users/Wareen/HawEditRootedControllerMap-94d9478-20261014/serena-map.json,
  SHA7eb590084ba8ca0f0965e42d2fdaa61aab972cb5b8a14843bd297ac429853cec.
- WslOmniAsrProducer.transcribe currently cuts source audio then runs a shared
  directory bridge. It does not adopt the rooted controller and must not be used
  as a shortcut for protected execution.
- asr_worker.run_request loads the champion/CTC, preserves strict canonical
  assembly and optionally uses worker_journal/ResumableBackend/Validator. It
  writes staging/checkpoint/final files. These writes cannot succeed unchanged
  in the immutable private root. Separate inference from persistence narrowly;
  keep all semantic/completion/origin/adapter checks and CLI behavior.
- RootedCommand currently caps its declaration at4096files. Complete copied
  base Python works; complete Torch/SDK/model/driver closure has not run. Do not
  infer complete SDK admission from a base interpreter diagnostic.
- Registry/broker cap lifetime30s/64births/32requests. Diagnostic results cap64KiB.
  None is sufficient authority for a full source/model run; launch-plan.md
  explicitly reserves the later separately admitted producer unit.
- GPU worker Landlock is mandatory. Applying the current controller GPU
  Landlock before service prevents opening original comm leaves. A broader
  writable proc subtree or omitted worker policy is not an acceptable shortcut.
- Proposed narrow fix: controller uses its existing non-GPU broker fence while
  servicing (no controller GPU opens), then final GPU Landlock before Snapshot
  return. Its stronger inherited open denial changes negative-probe errno:
  production must separately prove genuine Landlock denial on the fixed direct
  entropy leaf using the exact permitted broker open shape, and separately prove
  original-description alias refusal. Keep default EACCES checks unchanged;
  no blanket EACCES-or-EPERM acceptance or caller readiness flag.

## Fresh Local Readiness And Limits

`python -m hawedit.models` reports missing current-source WSL receipt, absent
Community-1 weights, and no cloud keys in this shell environment. Independent
secure read_credential calls return Gemini configured:true/HF token configured:true.
No credential value was printed or modified; no key-validation/provider call.
Presence is not validity, licence acceptance, governance or spending authority.
No checkpoint is declared absent merely because a source receipt is missing.
BLOCKED #24 current independent VEX review remains expired/source-mismatched;
do not rebind its digest or renew its date without actual qualified review.
BLOCKED #4 gated access/rights must be resolved without inferred licence consent.
Existing US$5 transcript-only Gemini scope remains the sole paid-test ceiling.

BLUEPRINT §§2-5,§7,§§8.1-8.3; D-263 delivery, D-274 episode state, D-329 private
lifecycle. This research does not grant broader resources, GPU policy, model
release, installation, cloud video sharing, publication or acceptance.

## PA1 Service Follow-Up At 86f9c12

Actual nine Serena pairs, unchanged source:
C:/Users/Wareen/HawEditGPUServiceMap-86f9c12-20261014/serena-map.json,
SHA25600c51d6fabd236ad5f49df206f52bb438af54004d1a0a7956613db539de4c304.
Current _run opens its task root through readonly proc. Successful original
registry fixture instead holds the original private /proc/2/task before that
transition. Anchor only that stopped original worker's task root inside typed
launch custody; worker receives no task directory, writable proc or host paths.
Prove genuine CPU/GPU comm service and exact foreign-target refusals, then full
drain/final controller GPU Landlock/fence/inspection before result publication.
External detailed research: C:/Users/Wareen/HawEditGPUServiceResearch-86f9c12-20261014.md.

Community-1 is now really provisioned under the approved row exception; see
evidence/community1-provisioning-20261014.md. Full86f9c12 gate6408pass/2fail:
strict absent-checkpoint test assumed global absence, plus independent VEX.

Actual WSL cgroup metadata shows no active delegated writable limits, not an
exhaustive impossibility proof. Dedicated existing Python3.12.0 children really
refuse256MiB allocation under RLIMIT_AS128MiB and hit kernel SIGKILL under
RLIMIT_CPU1s hard ceiling. Raw C:/Users/Wareen/HawEditResourceLimits-research-86f9c12-20261014.json,
SHA256882e81e663b0f1f156875f6e2f748367902b4b9db8fc56b615e6a2d9aa9c03c9.
These are process-local research proofs, not full-worker RSS/VRAM/effect limits
or admission. No privileged configuration. References consulted2026-10-14:
https://docs.kernel.org/admin-guide/cgroup-v2.html and
https://man7.org/linux/man-pages/man2/getrlimit.2.html. Do not claim RLIMIT_RSS
is effective isolation or assume cgroup delegation is the only possible guard.

## Positive GPU Test Evidence Correction

At75f3a58, GPU fixture null stderr is required by outside-FD isolation but can
hide a late controller failure after the worker already exits. Parent Scope
worker-death observation alone does not prove init's final assertions. Do not
count earlier GPU green rows as authenticated controller completion. Cancelled
the in-flight75f3a58 gate by verified exact pytest child37968 only, no control
characters or process-group signal; no fresh completed JUnit/gate pass exists.
Raw cancelled log SHA256e9950e42a2d12b1995f728c14cb8cb9a2fa7b7f5a6becf9bbcf81c593421de74.
Strengthen tests with a separate original fixed unnamed SEQPACKET acknowledgment
using existing strict GPU control_fds rules, original init kernel credentials
and exact case-bound packet after every final assertion. Worker receives no
channel at exec; no production policy/code or outside-FD relaxation. Real init
death before final acknowledgment must make the fixture refuse, not pass.
