# Pinned revision is not proof of local checkpoint bytes

> Measured 2026-08-09 on hawapc01. Decision: D-096.

Before this change, HawEdit pinned each Hugging Face repository to a full commit, but a nonempty
directory counted as available and every loader trusted whatever bytes were inside it. A truncated
download was likely to fail later; a same-size changed tensor or an added modelling file was not
distinguishable from the intended snapshot at all.

## Content identities

`models/integrity.json` was generated from the Hugging Face Hub API with `files_metadata=True` at
the exact commits already fixed in `models/revisions.json`. It accounts for every
`Provisioning.WEIGHTS` entry in the registry. Five snapshots have complete content identities;
pyannote's public inventory is visible but the gated API redacts all five LFS digests:

| Model | Commit | Files | Bytes |
|---|---|---:|---:|
| `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` | `d71490a623113b4b069ac07cfc85b409389dde4c` | 21 | 10,095,911,962 |
| `Qwen3-VL-Embedding-2B` | `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda` | 18 | 4,271,068,726 |
| `Qwen3-VL-Reranker-2B` | `4bd860ac4f15ad1897a214615cccc700f8f71818` | 20 | 4,271,056,557 |
| `MCG-NJU/VideoChat3-4B` | `37fa901ec5913f84bc31108ebc1e60ad1903634c` | 28 | 8,960,941,813 |
| `MCG-NJU/TimeLens2-4B` | `ddbb6cb944f13ce21e59e85da23c5f356107260e` | 18 | 9,670,001,504 |
| `pyannote/speaker-diarization-community-1` | `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` | 10 inventory entries; 5 LFS digests **blocked** | 33,695,573 |

For accessible LFS objects the manifest records the content SHA-256 published in LFS metadata.
The five redacted pyannote values are represented as `hub_digest_redacted: true`, never as fake
asterisk checksums, and the model's status is `blocked`. Ordinary Git objects use the repository's
canonical blob identity: SHA-1 over `blob <size>\0` plus the bytes.
That SHA-1 is an upstream object identifier, not a new cryptographic-strength claim. A second
preimage for an already fixed blob is outside this threat model; release authenticity remains a
separate M3.7 shortfall.

## Runtime enforcement

`ModelStore.verify_checkpoint` now requires all of the following before a HawEdit-owned loader can
import or invoke the model stack:

- manifest repository and revision exactly match the provisioning manifests;
- the regular-file set exactly matches the remote snapshot (download cache metadata excluded);
- no checkpoint path is a symlink and no manifest path can escape the directory;
- every file has the exact published size and content identity.

The guard is wired into the Qwen embedder, Qwen reranker, VideoChat3, TimeLens2 and Sorani Qwen-ASR
validator. A future pyannote loader cannot pass verification while its status is blocked. The
readiness report uses the same proof: a nonempty but unverified directory is now reported
unavailable rather than ready. Installed wheels carry the integrity manifest alongside the source
and revision manifests.

The regressions include exact Git/LFS success, same-size tensor corruption, missing and added
files, provisioning/manifest revision drift, complete registry coverage, installed-wheel data and
proof that each adapter reaches integrity enforcement before Torch/Transformers/Qwen-ASR loading.

## Real local proof and cost

The production verifier read every byte of the five checkpoints installed on hawapc01:

```text
PASS rzgar/qwen3-asr-sorani-kurdish-ckb-v1  21 files  10,095,911,962 bytes   8.567 s
PASS Qwen3-VL-Embedding-2B                  18 files   4,271,068,726 bytes   3.719 s
PASS Qwen3-VL-Reranker-2B                   20 files   4,271,056,557 bytes   3.679 s
PASS MCG-NJU/VideoChat3-4B                  28 files   8,960,941,813 bytes   7.628 s
PASS MCG-NJU/TimeLens2-4B                   18 files   9,670,001,504 bytes   8.352 s
TOTAL                                      105 files  37,268,980,562 bytes  31.946 s
```

The loader cost is intentional and occurs once per lazily loaded model instance. Hashing only a directory
listing, size or mtime would make the same-size corruption regression pass. Pyannote remains absent
because its download is gated (`BLOCKED.md` #4); its exact inventory is pinned now so the same proof
will apply only after accepted repository access exposes the five missing LFS identities.

## Boundary

This closes local-byte integrity for project-managed checkpoints. It does not sign the Git commit,
wheel or manifest, and it does not cover model-card assets downloaded internally by the
package-managed OmniASR runtime. Those remain explicitly named in M3.7 rather than being hidden by
the new checksums.
