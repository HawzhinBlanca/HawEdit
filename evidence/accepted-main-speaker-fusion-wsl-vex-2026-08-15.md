# Speaker-fusion main WSL ASR/VEX acceptance — 2026-08-15

This is local production-host execution evidence for merged `main` commit
`99e91de56f4ca028a44d2029d0bc64514418aedf`. It is not a substitute for the required hosted
`wsl-asr-security` job and it is not an ASR accuracy claim.

## Promotion state

- PR: `https://github.com/HawzhinBlanca/HawEdit/pull/4`
- merged `main` SHA: `99e91de56f4ca028a44d2029d0bc64514418aedf`
- pull-request gate run: `31856880380` — Python 3.12 and canonical gate succeeded
- protected-main gate run: `31857278626`
- protected-main run state at measurement time: queued because the repository reported zero
  self-hosted runners; no queued job was bypassed or relabelled

## Exact source-bound runtime

The reviewed source fingerprint is
`f2007b91a325d8453a519b32b6ffcb545e5ef81611b8761e07256911d16f1476`. Running the supported
source-forced setup path completed in 261.7 seconds. Its final probe reported:

- OmniASR import succeeded;
- two CUDA GPUs were visible; and
- the ready runtime was published under the application-managed WSL runtime root.

## Live VEX result

The source-forced command was:

```text
PYTHONPATH=src python -m hawedit.wsl_vex_gate --distro Ubuntu --evidence <new path>
```

It completed in 186.7 seconds with status `accepted`. The write-once 10,382-byte JSON artifact had
SHA-256 `9e4e1116a5d77d9733a4fda394d739b234d57b5309ad6794e7649c0eda11317f`.

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

The scanner environment was independently bound: pip-audit 2.10.1, 29 exact wheel
distributions, scanner inventory SHA-256
`b20c9ba80b886f9f64845197dcd6e88158ad0c126eb4bfd71e6d913e9e30ad6c`, and OSV service
`https://api.osv.dev/v1/query`.

## Remaining boundary

This result proves source/dependency/asset/vulnerability-policy acceptance on hawapc01. It does
not prove:

- the required hosted artifact upload, because no repository self-hosted runner was registered;
- a new 38-minute Stage 1 run, because an independently owned `cortex_7b_server.py` workload held
  about 17.5 GiB on each 24 GiB GPU during this measurement; or
- CER/WER, dialect coverage, editorial quality, or active-speaker accuracy, which require the
  authorised human-reference datasets in `BLOCKED.md` #1.

No unrelated process was terminated to obtain this result.
