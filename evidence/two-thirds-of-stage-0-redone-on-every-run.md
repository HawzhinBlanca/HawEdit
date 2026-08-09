# Stage 0 repeated-work and atomic-reuse evidence

Date: 2026-08-10. Decision: D-162. Upstream adversarial pass: #19 / D-132.

## Real-media measurement

The upstream pass measured `ZAR38MinTest.mp4` (82,446,418 bytes, 2,313.7 seconds):

| pass | first run | repeated run before reuse |
|---|---:|---:|
| audio extraction | 69.9 s | 69.5 s |
| proxy extraction | 30.3 s | 30.3 s |
| complete Stage 0 | 151.4 s | 100.2 s needlessly repeated |

Hashing the source took 0.1 seconds. After verified reuse, the two repeated extraction passes took
0.2 seconds and neither artifact was rewritten. The reused WAV still decoded as 16 kHz, mono,
16-bit PCM.

## Readiness-branch publication contract

Reuse requires all three recorded facts to match the current state:

1. SHA-256 of the source bytes;
2. the ffmpeg command with its private/final destination abstracted out; and
3. the completed output byte count.

The readiness adaptation adds failure atomicity and serialization. A safe single-link lock protects
each final artifact. ffmpeg writes a unique same-directory file with the real container suffix. The
source is hashed again after encoding; missing/empty output and a changed source are refused. Only a
complete output is atomically moved to the final name, followed by individually atomically replaced,
fsync'd JSON provenance. An encode or source-validation failure leaves the preceding artifact and
provenance untouched; an interrupted pair publication is detected on the next call and never reused
without a matching record.

## Discriminating regression evidence

`tests/test_ingest.py` proves:

- identical source and command reuse without rewriting;
- changed bytes at the same source path rerun;
- command drift and output truncation rerun;
- a failed rerun preserves the last good pair and removes its private file;
- source mutation during encoding cannot publish;
- success without output is a domain failure;
- cache reuse cannot bypass the Stage 1 WAV-format check;
- a hardlinked lock cannot modify its victim; and
- two concurrent reruns encode once and then reuse.

Focused verification: `34 passed`; Ruff and strict mypy clean. Canonical full-gate and exact-SHA
hosted evidence are recorded only after this source change receives them.
