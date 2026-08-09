# OmniASR package-asset integrity · 2026-08-09

## Finding

The official `omnilingual-asr==0.2.0` cards point at three mutable HTTPS URLs. Installed
`fairseq2==0.6` derives each cache directory from the first 24 hexadecimal characters of
SHA-1(URL), returns an existing directory without hashing it, and checks only HTTP
`Content-Length` on a first download. That proved the address, not the model bytes.

The card store also accepts system and user metadata. A trailing `@` on the two model card names
disables their environment lookup, but their `tokenizer_ref` is resolved by a bare name, so a
user card could still redirect the tokenizer. A changed same-version package card could redirect
checkpoint URLs or add `restrict: false`. Finally, fairseq2 returns a directory instead of the
expected file when that cache directory contains more than one member.

## Reviewed identities

The deployed WSL runtime and the upstream HTTPS `Content-Length` agree exactly:

| Asset | fairseq2 cache key | Bytes | SHA-256 |
|---|---|---:|---|
| `omniASR-LLM-7B-v2.pt` | `116c2dd9dc4cf95c0aac590e` | 31,220,488,063 | `1b29a4045ddfbe9125e6c9d465d5bc29063eea256ace37c129742edc07aed17a` |
| `omniASR-CTC-3B-v2.pt` | `0a31b71a234e317bd6f84e33` | 12,325,920,624 | `fa7f662c326842bb80561db97631ae3c48d911aec579654a1e8414c26caf9089` |
| `omniASR_tokenizer_written_v2.model` | `e7be1a6acb8f76fdbca19dce` | 91,481 | `8aa11a1092142ef472537476ef6e76541123e2f0d789b79f3ebd119008240b1e` |

Total: **43,546,500,168 bytes**. The official card document
`omnilingual_asr/cards/models/rc_models_v2.yaml` is 2,725 bytes, SHA-256
`af4d63febb0569831210e470b256ec70dc3a55065756c21c1f514d0001f283ed`.
The live S3 version ids observed through the official CloudFront URLs were respectively
`cKPcHujn3wvkUmsh_JFayXIsU0CTHNYO`, `rMQ3ABjZt5zo2sNKVH3._LImPtXjdtaf`, and
`g9RvMamoBHe0XTWuBNlqEiCUIummoBX7`; SHA-256, not those mutable transport headers, is the
application identity.

One native WSL `sha256sum` pass over all three files completed in 170 seconds. A second
application verifier pass benefited from the OS page cache. No hashing is done through the much
slower Windows UNC bridge; the canonical worker performs it inside WSL before model construction.

## Enforcement

`src/hawedit/omni_assets.py` is the packaged, source-fingerprinted allowlist. Setup downloads each
missing file to a private directory, enforces HTTPS final location, HTTP status, announced size,
actual size and SHA-256, flushes it, makes it read-only and atomically renames the directory into
fairseq2's exact cache key. A corrupt existing directory is never silently replaced; the operator
is told which exact directory to move aside before retrying. An interrupted or mismatched download
leaves no public fairseq2 entry.

Before either model pipeline is constructed, the worker:

1. hashes all 43.5 GB again through no-follow regular-file descriptors;
2. rejects symlinks, hardlinked model assets, mutation during hashing, and every extra directory
   member;
3. requires `omnilingual-asr==0.2.0`, `fairseq2==0.6`, and the exact installed card bytes;
4. points both fairseq2 external card sources at distinct existing verified-empty private dirs;
5. resolves and compares every effective model/tokenizer field, including architecture, family,
   URI, bare tokenizer reference and the absence of `restrict: false` or other added fields; and
6. loads through suffix-preserving private aliases to the verified open descriptors, holding those
   descriptors until both pipelines exist, so a pathname swap after hashing cannot change the
   bytes fairseq2 opens.

The setup command no longer treats `.ready` as permanent asset evidence: every rerun provisions or
rehashes the assets and refreshes/verifies the fingerprinted worker source. It invalidates an old
readiness marker before changing the shared runtime and atomically publishes a new marker only
after package imports, asset checks and the two-GPU probe succeed. The worker refuses a copied
source snapshot that no longer matches the host package. Empty cache environment variables are a
refusal rather than permission to provision 43.5 GB into the process working directory.

The descriptor binding closes rename/symlink replacement between verification and load; it is not
a kernel-enforced immutable snapshot. A malicious same-UID process that already has a writable
descriptor to the same inode remains outside this application-level supply-chain and accidental
corruption threat model. The installed package card may legitimately be hardlinked by `uv`; its
exact version, size and bytes are still enforced.

## Negative controls

Focused tests independently refuse same-size byte tampering, an extra cache member, corrupt-cache
network replacement, bad first-download digest, HTTP downgrade, changed upstream size, bare
tokenizer redirection, checkpoint URI drift, `restrict: false`, wrong package version, changed card
bytes, ambient system/user card paths, empty cache environment values, a failed stale-ready
revalidation, and a tampered ready worker snapshot. Successful controls cover the exact three
cache keys, cache-root precedence, atomic first download, a valid package-manager-hardlinked card
and effective official metadata.

Real WSL integration loaded the canonical tokenizer through the held alias and then constructed
the actual `Wav2Vec2LlamaModel` and `Wav2Vec2AsrModel` from all 43.5 GB through those aliases in
249 seconds. An independent small-checkpoint probe also exercised fairseq2's real
`BasicModelCheckpointLoader` and `TorchTensorLoader`, rather than a mocked URI consumer.

`omniASR_LLM_Unlimited_3B_v2` remains deliberately outside this allowlist. It is not installed and
has no independently measured reviewed SHA-256; adding an upstream card name is not provisioning.

Canonical gate after the unit: Ruff, formatting and mypy clean across 102 source files; **1,307
passed, 0 skipped**; fresh JUnit evidence accepted; `VERIFY OK`.
