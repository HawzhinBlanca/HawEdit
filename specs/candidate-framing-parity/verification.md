# Candidate framing parity verification

Baseline: `7fa7d3a37efb8f11d68ecc2b9a52ecd082f7535e`.
Owner approval and scope: plan.md. Decision: D-279. No completion claim.

## Evidence location

Private logs, scripts, JUnit reports, commands, runtime versions and file hashes:
`C:/Users/Wareen/HawEditQuality-7fa7-20261004/`.
Actual Serena definitions/references: `framing-impact-map.json` and
`framing-helper-before-map.json` and `framing-final-map.json`. The final map
captured ten symbol/reference queries with all mapped source hashes unchanged.
These maps supplement impact-map.md; static references do not resolve every
protocol dispatch.

## Test-first history

| Report prefix | Outcome | Interpretation |
|---|---|---|
| camera-red | 18 failed, 5 passed | Pre-fix reproduction, including two overbroad new-test MP4 assertions |
| camera-red-v2 | 20 failed, 5 passed | Split admission cases added; two new accounting expectations were incorrect |
| camera-first-green | 25 passed | First shared implementation; not final caller or gate evidence |
| camera-third-red | 4 failed, 25 passed | Third tracked speaker was still silently dropped in both routes |

All attempts remain preserved, not replaced. The new MP4 assertions originally
counted the required Stage 0 proxy as a deliverable; they were narrowed to actual
private/public output locations. The new accounting assertions originally
expected no record, whereas the synthetic judge generates one zero-token,
zero-cost editorial record; tests now assert that exact record. No existing
test, fixture or golden was changed. The new module became self-contained to
avoid mypy treating an imported test helper module as two module names.

The third-speaker failures preceded the source repair. Forced two-person split
now refuses more than two tracked speakers; automatic layout retains continuous
speaker framing rather than choosing only the first two identities.

Latest exact `bash scripts/verify.sh --fast`: exit 0, ruff passes and strict mypy
passes 317 source files. This is not the complete gate.

## Final checks and real-source retest

The full affected caller suite exited 0: 673 passed, zero failures/errors/skips,
JUnit time 925.681 seconds and wrapper wall time 928.319 seconds on HawaPC01.
`callers-checks/terminal.json` records the command, native CPython 3.12.10 and
library versions. Pipeline and new-test hashes were unchanged during the run.
JUnit SHA-256: `be6903b1370f8145d4b11b573dddafb82aeb662ea7377ecddaa5a3a054e063e7`.
This includes all 29 new cases and complete affected caller modules, not CI.
The planned clean-source full gate has not yet run for this implementation.
After a reviewed local commit, `gate-checks/terminal.json` will record the exact
canonical gate without command or interpreter overrides.

`retest_zar38.py` prepares a fresh full-source production ASR invocation through
the supported parser/build/run path. It is not yet executed at this checkpoint.
The terminal record will contain source and old canonical-raw hashes before and
after, refusal diagnostics and output inventory. No supplied transcript,
synthetic judge, direct-worker bypass, cloud route or approval is enabled.

## Limits

The 29 new cases use actual decoded existing fixture video with synthetic
transcript, discovery, judge and tracker inputs. Passing them cannot establish
ASR accuracy, true speaker identity, editorial preference or native readability.
No ZAR38 reel, published deliverable, signed acceptance, independent holdout,
performance improvement or 10/10 is claimed.

The previous exact gate failed the checked-in VEX source binding. A qualified
current-source security review remains BLOCKED #24; changing a digest, date or
expiry is not that review. The prior ZAR38 raw contains unresolved alignment
failures. Canonical model/decoder policy and all original media/raw are retained.
Other corpus, model-rights, reviewer and spending prerequisites remain explicit
in the owner packet. No ledger row is promoted, and no push or publication is
authorized by this local verification work.
