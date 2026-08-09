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
- source SHA-256 `540fa9c0a9f56b1d9ecda04761270fddbf018a1a255db46de7038c43b3c5d411`;
- build/runtime lock SHA-256 `b153285953b96583bf60945783364662f6ab58f8fc1cb6f58fbdd2caa454a9a9`
  / `190844f326d409b8d6b7b9536a880e2a77a9eebfe056369688337ce6386f5aea`;
- all three OmniASR assets verified: 43,546,500,168 bytes total;
- official OmniASR and Qwen-ASR imports succeeded;
- two CUDA GPUs visible.

## Final live VEX result

Command:

```powershell
.venv\Scripts\python.exe -m hawedit.wsl_vex_gate `
  --evidence .gate/wsl-asr-vex-540fa9c0.json `
  --distro Ubuntu --timeout-seconds 1200
```

Result: `status=accepted`, 12 findings, 12 dispositions, 12 matched dispositions.

- pip-audit `2.10.1`, OSV service;
- scanner inventory: 29 exact wheels, SHA-256
  `b20c9ba80b886f9f64845197dcd6e88158ad0c126eb4bfd71e6d913e9e30ad6c`;
- raw audit SHA-256 `f700054ba05a53744985ae36a8bf6b860d5f5096a0645214eb0393ee1d6eddd0`;
- reviewed policy SHA-256 `063b2669af43f2cbf10b746dd5557d9ee5a07942499cc021aa52fabc26255ec7`;
- receipt SHA-256 `12be11242a1e5329931d52bbe7c5ffa24db6adc3de3eb7955f557103fea97b85`;
- accepted evidence: 10,382 bytes, SHA-256
  `ea0a9889b8d521d092e5b3dc99f26ae413a3c2c36b1cc9bf4834cc3050474404`.

The VEX result does **not** claim a vulnerability-free environment. It proves that every finding in
the exact audited inventory has a current explicit disposition, including affected-but-mitigated
entries, bound to this source, dependency locks and model bytes. The policy expires 2026-09-08 and
must be reviewed again rather than silently reused. Native KenLM/Sox output reproducibility and
NVIDIA redistribution review remain separate supply-chain gaps.
