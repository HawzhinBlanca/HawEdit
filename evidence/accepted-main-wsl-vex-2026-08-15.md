# Accepted-main WSL ASR/VEX acceptance — 2026-08-15

This is local production-host execution evidence for the protected-main merge commit
`22da3a52536284a18965d51f5a88173c1c9d0c44`. It is not a substitute for the required hosted
`wsl-asr-security` job and it is not an ASR accuracy claim.

## Promotion state

- PR: `https://github.com/HawzhinBlanca/HawEdit/pull/2`
- accepted `main` SHA: `22da3a52536284a18965d51f5a88173c1c9d0c44`
- pull-request gate run: `31850633760` — Python 3.12 and canonical gate succeeded
- protected-main gate run: `31851073642`
- protected-main Python 3.12 job: succeeded
- protected-main `wsl-asr-security`: queued because the repository reported zero self-hosted
  runners; no job step had started at the time of this record

## Exact source-bound runtime

The first live command refused because no receipt existed for the accepted source fingerprint
`57145db2838e4d734159d36dab5a8c5fd0d6e4ec406dcb79a706da8d34c44f7d`. Running the supported
`hawedit-asr-setup --distribution Ubuntu` path then completed in 279.1 seconds. Its final probe
reported:

- OmniASR import succeeded;
- two CUDA GPUs were visible; and
- the ready runtime was published under
  `C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr`.

The refusal before provisioning is part of the evidence: the prior runtime generation was not
accepted merely because its dependencies or assets were still present.

## Live VEX result

The source-forced command was:

```text
PYTHONPATH=src python -m hawedit.wsl_vex_gate --distro Ubuntu --evidence <new path>
```

It completed in 188.3 seconds with status `accepted`. The write-once 10,382-byte JSON artifact had
SHA-256 `251a40c345fb312bf94eae855fc03fa45cb7f556d119ea53bfc535189eeb1201`.

Measured runtime identity:

| field | value |
|---|---|
| WSL distribution | Ubuntu |
| Python | 3.12.0 |
| CUDA devices | 2 |
| dependency inventory | 140 exact distributions |
| dependency inventory SHA-256 | `b6aaccbe1a13265dc91d5b99bc6f41ca62eaea4d2c6d884a81df6dacb1b77216` |
| runtime-lock SHA-256 | `190844f326d409b8d6b7b9536a880e2a77a9eebfe056369688337ce6386f5aea` |
| build-lock SHA-256 | `b153285953b96583bf60945783364662f6ab58f8fc1cb6f58fbdd2caa454a9a9` |
| OmniASR assets | 3 files, 43,546,500,168 bytes |
| findings | 12 |
| reviewed dispositions matched | 12 of 12 |
| VEX expiry | 2026-09-08 |

The scanner environment was also independently bound: pip-audit 2.10.1, 29 exact wheel
distributions, scanner inventory SHA-256
`b20c9ba80b886f9f64845197dcd6e88158ad0c126eb4bfd71e6d913e9e30ad6c`, and OSV service
`https://api.osv.dev/v1/query`.

## Remaining boundary

The result proves source/dependency/asset/vulnerability-policy acceptance on hawapc01. It does not
prove:

- the required hosted artifact upload, because no repository self-hosted runner was registered;
- the new 38-minute Stage 1 run, because a separate long-running `cortex_7b_server.py` held about
  17.5 GiB on each 24 GiB GPU at the time of acceptance; or
- CER/WER, dialect coverage, or editorial quality, which require the human-reference datasets in
  `BLOCKED.md` #1.

No unrelated GPU process was terminated to obtain this result.
