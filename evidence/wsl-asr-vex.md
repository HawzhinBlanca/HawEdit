# WSL OmniASR vulnerability dispositions · 2026-08-09

## Result

`security/wsl-asr-vex.json` is a **30-day, identity-scoped disposition**, not a claim that the
WSL dependency graph is vulnerability-free. A review-date OSV query for `torch==2.8.0` emitted
eight advisory families. `transformers==4.57.6` emitted seven records which collapse by aliases
to four distinct families. The checked policy covers all twelve families and expires on
2026-09-08.

The policy applies only while all of these remain exact:

- CPython 3.12 and `omnilingual-asr==0.2.0`, `torch==2.8.0`,
  `transformers==4.57.6`;
- build lock SHA-256
  `b153285953b96583bf60945783364662f6ab58f8fc1cb6f58fbdd2caa454a9a9` and runtime lock
  SHA-256 `190844f326d409b8d6b7b9536a880e2a77a9eebfe056369688337ce6386f5aea`;
- the three measured OmniASR assets: 31,220,488,063 bytes / `1b29a4…17a`,
  12,325,920,624 bytes / `fa7f66…089`, and 91,481 bytes / `8aa11a…b1e`.

`src/hawedit/vex.py` compares those values with the canonical WSL `.ready` receipt, parses
`pip-audit` JSON with aliases enabled, and refuses:

- an unknown finding or ambiguous disposition;
- an expired or future-dated review;
- lock, package, Python, or asset drift;
- a missing, added, or version-drifted audited distribution relative to the complete receipt;
- a disposition no longer emitted by the current audit (visible stale review state);
- duplicate JSON keys, duplicate IDs/aliases/dependencies, booleans in integer fields,
  coercible strings, unknown fields/statuses, missing controls, and malformed top levels.

The stale-disposition refusal is deliberate. Feed removals and ID re-keying require review just
as additions do; this gate does not quietly treat disappearance from one feed as remediation.

## Honest disposition summary

| Family | Status | Basis |
|---|---|---|
| CVE-2025-3001 / `torch.lstm_cell` | **affected** | The direct API is not exposed, but absence from every transitive model call was not proven. |
| CVE-2025-3000 / `torch.jit.script` | **affected** | No caller-supplied TorchScript; transitive non-use is not claimed. |
| CVE-2025-2999 / `unpack_sequence` | **affected** | ASR processes sequences, so bounded request and segment controls mitigate without an unreachable claim. |
| CVE-2025-55551 / `torch.linalg.lu` | **affected** | No direct API exposure; full transitive non-use is not proven. |
| CVE-2025-55552 / image rotation interaction | **not affected** | The isolated product is audio-only and exposes no image augmentation or tensor-operation API. |
| CVE-2025-55554 / numeric conversion | **affected** | Audio can influence tensor values; the review therefore keeps the affected label. |
| CVE-2026-4538 / PT2 loader | **not affected** | No PT2 archive is accepted or loaded; only the three allowlisted assets enter model construction. |
| CVE-2026-24747 / weights-only unpickler | **affected, mitigated** | The loader is relevant. Exact checkpoint bytes, no-follow hashing, descriptor binding, card integrity, and path/type checks are the controls. |
| CVE-2026-4372 / remote kernel config | **affected, mitigated** | The installed Transformers version is affected; HawEdit recursively rejects the bypass fields before loader dispatch. |
| CVE-2026-1839 / `Trainer` RNG restore | **not affected** | The worker is inference-only, has no `Trainer`, and uses Torch 2.8 (the advisory requires Torch below 2.6). |
| CVE-2026-5241 / LightGlue nested loader | **not affected** | LightGlue is outside the model-type allowlist and nested remote-code fields are rejected. |
| CVE-2025-14929 / X-CLIP conversion | **not affected** | No X-CLIP model or conversion path exists in this audio-only runtime. |

The five **affected** tensor-operation findings retain residual risk: isolation, schema boundaries,
fixed code/model identity and sub-40-second segments reduce exposure, but they are not a vendor
patch. CVE-2026-24747 is especially not called unreachable merely because checkpoint SHA-256 is
enforced. The vulnerable unpickler still executes; the control is that only independently measured
bytes can reach it.

## Primary advisory material

- PyTorch issues and patches for
  [CVE-2025-3001](https://github.com/pytorch/pytorch/issues/149626),
  [CVE-2025-3000](https://github.com/pytorch/pytorch/issues/149623),
  [CVE-2025-2999](https://github.com/pytorch/pytorch/issues/149622),
  [CVE-2025-55551](https://github.com/pytorch/pytorch/issues/151401),
  [CVE-2025-55552](https://github.com/pytorch/pytorch/issues/147847),
  [CVE-2025-55554](https://github.com/pytorch/pytorch/issues/151510), and
  [CVE-2026-4538](https://github.com/pytorch/pytorch/pull/176791).
- PyTorch's
  [GHSA-63cw-57p8-fm3p](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p)
  and the [2.10.0 release](https://github.com/pytorch/pytorch/releases/tag/v2.10.0) for
  CVE-2026-24747.
- Hugging Face fixes for
  [CVE-2026-4372](https://github.com/huggingface/transformers/commit/a7f8e7ff37d87d1a1a0c8cf607971c607741452f),
  [CVE-2026-1839](https://github.com/huggingface/transformers/commit/03c8082ba4594c9b8d6fe190ca9bed0e5f8ca396), and
  [CVE-2026-5241](https://github.com/huggingface/transformers/commit/676559d5022b74aaa0cee1cee0842b7f27c5320e).
- The issuer's [ZDI-25-1144](https://www.zerodayinitiative.com/advisories/ZDI-25-1144/)
  for CVE-2025-14929.

## Integration handoff

This lane does **not** claim CI integration or complete vulnerability closure. The workflow owner
should produce the report inside the provisioned WSL environment with the exact audited tool and
then run the packaged policy gate on the host. A bounded command shape is:

```bash
uvx --from pip-audit==2.10.1 pip-audit \
  --strict --vulnerability-service osv --format json --aliases on --desc off \
  --progress-spinner off --path "$WSL_VENV/lib/python3.12/site-packages" \
  > "$REPORT" || test "$?" -eq 1
```

```powershell
python -m hawedit.vex `
  --report $REPORT `
  --receipt $WSL_RUNTIME\sources\<source-generation>\.ready `
  --vex security\wsl-asr-vex.json
```

The integration must retain `pip-audit`'s JSON even when its expected finding exit code is 1,
must not use `--ignore-vuln`, and must fail if `hawedit.vex` exits nonzero. The placeholder paths
must be obtained from the canonical runtime/receipt owner rather than guessed.

This command validates the contents and exact identity asserted by its two input artifacts; it
does not itself invoke WSL, rehash 43.5 GB, or cryptographically attest who produced the report.
The workflow must first run the existing canonical live-receipt verification and must generate the
audit report in the same protected job. Supplying forged report and receipt files is outside this
four-file lane's trust boundary.
