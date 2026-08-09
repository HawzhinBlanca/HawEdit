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
