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
