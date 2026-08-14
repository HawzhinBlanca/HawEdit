# Release text-byte integrity acceptance — 2026-08-10

## Finding

The source gate and exact-SHA hosted gate were green at `fb17959`, but a clean local wheel built
from that commit could not audit its own installed dependency lock.  On this Windows checkout,
`core.autocrlf=true`; `git archive` exported unclassified `.txt` members with CRLF even though the
committed blobs and `HOST_LOCK_SHA256` identities were LF.

For `requirements/host-base-windows-py311.txt` the committed blob was 1,684 bytes with SHA-256
`89fbf3385563f9cbc407daf7997c2b39013caf8c95f33586b7da0500bbebe0c8`.  The wheel member was
1,707 bytes with 23 CRLF pairs and SHA-256
`aa7acdd9479c04e7b585a5aae4e6a235ec1512f6ee41aeda364614e9955ac97e`.  The installed resolver
correctly refused it.  This was an artifact-production defect, not a reason to weaken the digest.

## Fix and regression

Commit `9322f28` classifies `.gitattributes` and every tracked `*.txt` as `text eol=lf`.  The
release regression forces `core.autocrlf=true`, exports every tracked `.txt` through Git archive,
and requires each archive member to equal its committed Git blob byte-for-byte.  It covers the
release-build lock, all 13 host locks and the font license.

The exact committed wheel was independently built twice through `scripts/build-wheel.sh`:

- revision: `9322f28ddfbf0dd4c9afaaa7ea7bcce023334c32`
- wheel: `hawedit-0.1.0-py3-none-any.whl`
- size: 486,679 bytes
- SHA-256: `3ebf0e8416fcd0b5f4e5e238f78106fabb8e7dc5a020360a615b24215e256845`
- builder: Python 3.12.10, pip 26.2.1, setuptools 84.0.0
- source epoch: 1,786,350,469

The corrected packaged Python 3.11 base lock is 1,684 bytes, contains zero CRLF pairs and has the
committed trusted SHA-256 `89fbf338...be0c8`.

## Installed-wheel acceptance

Fresh external venvs used the supported CPython 3.11.15 and 3.12.10 interpreters.  Each proof:

1. installed only the exact local wheel with `--no-index --no-deps`;
2. resolved the packaged target-specific base lock through `hawedit.environment`;
3. installed the dependency graph with `--require-hashes --only-binary=:all:`;
4. passed `pip check` and the exact installed-environment audit;
5. resolved seven authenticated installed data members from outside the checkout; and
6. started all nine installed console entry points with `--help`.

Both runs ended `SMOKE_OK`: Python 3.11 used `host-base-windows-py311.txt`; Python 3.12 used
`host-base-windows-py312.txt`.  This is local artifact acceptance.  GitHub OIDC attestation and a
durable release still require the protected-main release workflow; this evidence does not claim
either external event occurred.
