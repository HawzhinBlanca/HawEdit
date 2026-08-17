# Live WSL ASR dependency and VEX acceptance — 2026-08-09

This is measured deployment evidence from hawapc01, not a mocked test. The final run used the
current `src/hawedit` snapshot and Ubuntu WSL on the two-RTX-3090-Ti production host.

## Failures the native run found first

1. `uv venv --python 3.12` selected CPython 3.12.13. OmniASR 0.2.0 declares
   `Requires-Python <=3.12`, so `uv pip check` correctly rejected 3.12.13. The isolated runtime is
   now pinned to exact `3.12.0`, and that interpreter version is part of the environment digest.
2. Failure cleanup called Windows `shutil.rmtree` over a Linux `lib64` link and masked the domain
   error with `WinError 1920`. Cleanup now validates one direct unpublished generation and falls
   back to WSL `rm` only for that exact child.
3. The setup/import probe wrote `__pycache__` into its receipt-bound worker snapshot. Exact source
   revalidation then refused the snapshot. Setup, live probing and the Stage 1 worker now set
   `PYTHONDONTWRITEBYTECODE=1`; the allowlist verifier was not weakened.
4. OSV emitted repeated Transformers rows for one advisory identity with different affected-range
   `fix_versions`. The parser now canonicalizes only repeated package/version/primary/alias
   identities. Conflicting aliases still refuse, and the raw report remains SHA-bound.

## Final provisioning result

Command:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m hawedit.wsl_setup --distribution Ubuntu
```

Measured result:

- CPython `3.12.0`.
- generation `Ubuntu-a3a875601325fe6bd6497791`;
- 140 exact installed distributions; `uv pip check` reported all compatible;
- `kenlm==0.3.0` and `sox==1.5.0` built as the two explicitly reviewed sdist exceptions;
- source SHA-256 `aa651eeb520967ee7a8c195508ce863741a7563a336eaf18ec87a997a96ae3db`;
- build/runtime lock SHA-256 `b153285953b96583bf60945783364662f6ab58f8fc1cb6f58fbdd2caa454a9a9`
  / `190844f326d409b8d6b7b9536a880e2a77a9eebfe056369688337ce6386f5aea`;
- all three OmniASR assets verified: 43,546,500,168 bytes total;
- official OmniASR and Qwen-ASR imports succeeded;
- two CUDA GPUs visible.

## Final live VEX result

Command:

```powershell
.venv\Scripts\python.exe -m hawedit.wsl_vex_gate `
  --evidence .gate/wsl-asr-vex-aa651eeb.json `
  --distro Ubuntu --timeout-seconds 1200
```

Result: `status=accepted`, 12 findings, 12 dispositions, 12 matched dispositions.

- pip-audit `2.10.1`, OSV service;
- scanner inventory: 29 exact wheels, SHA-256
  `b20c9ba80b886f9f64845197dcd6e88158ad0c126eb4bfd71e6d913e9e30ad6c`;
- raw audit SHA-256 `d61cf8934ca504bea4a61dff2ec2bcf4610e9c10ac0297d3ce60aed341b96a1d`;
- reviewed policy SHA-256 `41f1314207c1d1ccce876d67d9fb4beccc53f96bd281428dd8d347f7f9682e31`;
- receipt SHA-256 `39985fd0e5280d1dff216c298cb332281bad246e03964b8b7645ffb9c604bfcf`;
- accepted evidence: 10,382 bytes, SHA-256
  `d0ec1a240dcbed17a6f248b6641e26c8b7250fbd2161272d61bc3b6646b9cc6d`, observed at
  `2026-08-09T14:47:17Z` in `.gate/wsl-asr-vex-aa651eeb.json`.

The VEX result does **not** claim a vulnerability-free environment. It proves that every finding in
the exact audited inventory has a current explicit disposition, including affected-but-mitigated
entries, bound to this source, dependency locks and model bytes. The policy expires 2026-09-08 and
must be reviewed again rather than silently reused. Native KenLM/Sox output reproducibility and
NVIDIA redistribution review remain separate supply-chain gaps.

## Exact-source refresh — 2026-08-10

The acceptance was repeated after the production-readiness branch moved to
`e80ab9a1081f34cc866e7811cdd3a0129527d010`. Documentation commits do not enter the worker source
digest; the exact `src/hawedit` snapshot accepted here is
`a131c2531f83f135fadc693a1e3bb8354066d9173fa8e154d091084a597ece06`.

Provisioning completed in 237.8 seconds and reused generation
`Ubuntu-a3a875601325fe6bd6497791`. The live receipt revalidated CPython 3.12.0, all 140 exact
distributions, 43,546,500,168 bytes across the three canonical OmniASR assets, and two CUDA
devices. Receipt SHA-256:
`fef9aa333e96c83847eded4799fbadba9462c5e5a667040e17409711df1a4a72`.

The separate live VEX gate completed in 154.5 seconds at `2026-08-10T01:24:32Z` and accepted 12
findings against 12 matched dispositions. The raw OSV report SHA-256 is
`2a90ab86207d376e763a733a62ada3f2dab59b49429a948cb058ff5120f0a21e`; the reviewed policy SHA-256
is `2d498c30f078078b7525bba1402e4044aadad05cb6daa3cf80e4f9d9d9bbb771`; and the 10,382-byte
write-once evidence JSON SHA-256 is
`11b0ff5d18b3060469f89680f9cc2cd112818cb3901556cba1501dc2d893f450`.

The exact commands were:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\hawedit-asr-setup.exe --distribution Ubuntu
.venv\Scripts\python.exe -m hawedit.wsl_vex_gate `
  --distro Ubuntu `
  --evidence .gate/wsl-asr-vex-e80ab9a1081f34cc866e7811cdd3a0129527d010.json
```

This closes current-machine receipt/VEX drift for the stated source snapshot. The protected
`wsl-asr-security` job remains intentionally unaccepted on this feature-branch dispatch: its policy
requires an official `push` to `main`, so post-merge hosted execution and artifact upload are still
required before release promotion.

## Delivery-integrity source refresh — 2026-08-10

The live acceptance was repeated at clean, ratcheted commit
`7257d5bba69ae6ab0e8e0c7b75b4cd0f64b7bbe8`, after hardening the SRT delivery boundary. The exact
receipt-bound `src/hawedit` SHA-256 was
`2250be4048e48fd7528660dcca1602dc5fa41b3f7a032fb1eee22ef26c4b83cc`.

`hawedit-asr-setup --distribution Ubuntu` completed in 165.7 seconds, reused generation
`Ubuntu-a3a875601325fe6bd6497791`, and revalidated CPython 3.12.0, all 140 distributions, all
43,546,500,168 OmniASR asset bytes, and two CUDA devices. The published receipt SHA-256 was
`7b926378d60af58bb7d59e3e1e0c08f7e5e9df7639b94a2a2586a2dc2681cfdb`.

The hash-locked live VEX gate then completed in 154 seconds and accepted 12 findings against 12
current matched dispositions at `2026-08-10T02:03:47Z`. The raw OSV report SHA-256 was
`126d97f8343cf9f84d772658e7d5ca70137711d205671fd7314714cdb6cf187f`; the reviewed policy SHA-256
was `0ab76e4d3a8aa927f9330246407d6e844a990048e049ad2b8281b8e7705da17e`; and the 10,382-byte
write-once evidence JSON SHA-256 was
`3b1231d44ad26080ab5d90020bdd7ee27a42c6931b5755d7f5c205a59e2533e5`.

The evidence is retained locally at
`.gate/wsl-asr-vex-7257d5bba69ae6ab0e8e0c7b75b4cd0f64b7bbe8.json`; `.gate` remains ignored because raw
machine evidence contains host-specific runtime details. This result is local production-host
acceptance only. The protected hosted `wsl-asr-security` job still requires an official push to
`main` and remains a release-promotion prerequisite.

## High-frame-rate delivery source refresh — 2026-08-10

The receipt and live VEX gate were repeated at clean, ratcheted commit
`c8c83b22f1379fcc6d210f20f9fb8aa7926c6682` after adding 60000/1001 drop-frame delivery. The
receipt-bound source SHA-256 was
`7ea0bb130dcca19afcff0c2395e4e4e40917dfa97c8e481b1e2cabd9742fec8c`.

Provisioning completed in 172.3 seconds and revalidated generation
`Ubuntu-a3a875601325fe6bd6497791`: CPython 3.12.0, 140 exact distributions, all
43,546,500,168 canonical OmniASR asset bytes, successful OmniASR import, and two visible CUDA
devices. The published receipt SHA-256 was
`08c2cc9268c747aa47fc064948c0454e8449937087884e1c1e4f1fbafd14c7b7`.

The isolated live VEX gate completed in 154.6 seconds at `2026-08-10T02:44:49Z` and accepted all
12 findings against 12 current matched dispositions. The raw OSV report SHA-256 was
`5059a8dde065f9c0df10fb0f775e1c60a5a9077c2fa8b30e957c78bbe21ad5e9`; the reviewed policy
SHA-256 was `64d35516bcdc31a593b3d2aab05fd03ea8d1a319afbb008eac84d19896fea9c0`; and the 10,382-byte
write-once evidence SHA-256 was
`6b744c49d672168aac5403624d09cb885d809c0ac9e082e12962d8c40dd2ab3e`.

The raw host-specific artifact remains ignored at
`.gate/wsl-asr-vex-c8c83b22f1379fcc6d210f20f9fb8aa7926c6682.json`. This refresh is local
production-host acceptance. The main-only hosted `wsl-asr-security` job and its uploaded artifact
remain a release-promotion prerequisite after merge.

## Main-history integration source refresh — 2026-08-10

The receipt and live VEX gate were repeated at merged readiness commit
`fd94f3afb171a57952a1f4770605b02dc28c0780`, whose history contains protected main through
`ba52888579f4873cfd9a60a84d7934544bfdeeb1`. The exact receipt-bound source SHA-256 was
`59dea49228ce34e1b124f16991fd206e7a265d1063e16b0b6f6d878812445c41`.

Provisioning completed in 172.8 seconds and revalidated generation
`Ubuntu-a3a875601325fe6bd6497791`: CPython 3.12.0, 140 exact distributions, all
43,546,500,168 canonical OmniASR asset bytes, successful OmniASR import, and two visible CUDA
devices. The published receipt SHA-256 was
`5f4f0e6ecdef5960bf971a7490050357e70cf8052b354af805b78768e4e17e5c`.

The isolated hash-locked VEX gate completed in 137.0 seconds at `2026-08-10T03:44:45Z` and
accepted all 12 findings against 12 current matched dispositions. The raw OSV report SHA-256 was
`338bdce68cef54f85630a87b94952a2b7fec853d09acc6aa7a1d699d7c7e7d5e`; the reviewed policy
SHA-256 was `656b0138aa63e7492bae17f46a4fc3a6122f1302770fdfca4e3bb3361b27c144`; and the 10,382-byte
write-once evidence SHA-256 was
`6122f459d107833068a567c3be1d2dd3f8cec2ca0bc2a7489377794ee8ecb201`.

The raw host-specific artifact remains ignored at
`.gate/wsl-asr-vex-fd94f3afb171a57952a1f4770605b02dc28c0780.json`. This is local production-host
acceptance. The protected hosted `wsl-asr-security` job still requires an official push to `main`;
the history join makes that merge possible but does not substitute for the main-only run.
