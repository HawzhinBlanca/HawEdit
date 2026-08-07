# Independent review — 2026-08-07

**Reviewers: Claude Sonnet.** Author: Claude Opus. That difference is the whole point — every
line of this project had been written and checked by one model, and the repository's own
`independent-review` gate exists to refuse exactly that. It could only be cleared honestly by
having a different model actually read the diff.

## Method

Six reviewers, one per dimension, each reading the real code and running Python against the
real modules: the five Kurdish invariants, the hosted-model boundary, pure-algorithm
correctness, whether the gate can be fooled, secrets and path handling, and code-versus-spec
fidelity to the frozen `BLUEPRINT.md`.

Every proposed finding was then attacked by **three independent skeptics** with distinct
lenses — does it reproduce, is it already guarded elsewhere in the call path, does the
blueprint actually require what it assumes. Two refutations killed a finding. Skeptics were
told to default to refuted when they could not demonstrate the defect.

**16 proposed · 11 survived · 4 blockers.**
55 agents, 3.9M subagent tokens.

## What survived

| Severity | File | Finding | Survived |
|---|---|---|---|
| blocker | `boundary.py` | assert_boundary_invariant accepts a non-boolean truthy sentence_complete, defeating Kurdish invariant #2's act | 2/3 |
| blocker | `gemini.py` | GeminiJudge.count_request_tokens() bypasses the mandatory ZDR governance gate | 3/3 |
| blocker | `gate.py` | hawedit.gate treats an all-skipped test run as valid "test evidence" and prints success | 3/3 |
| blocker | `credentials.py` | write_credential follows a symlink and writes the plaintext API key into a git-tracked file | 3/3 |
| major | `gemini.py` | gemini.py builds JudgeVerdict.self_contained with bool() truthiness coercion instead of the codebase's own _st | 3/3 |
| major | `render.py` | render_clip() never supplies the linked-libraries (ldd) evidence to assert_rtl_stack, so Kurdish invariant #4' | 3/3 |
| major | `gemini.py` | Transient network failures (OSError) are never retried — treated as a permanent refusal on the first attempt | 3/3 |
| major | `sentences.py` | Non-contiguous --sentences selection silently omits spoken content from captions and the shipped transcript wh | 2/3 |
| major | `credentials.py` | write_credential leaves the API key world/group-readable (0644) for a window before chmod(0600) | 3/3 |
| major | `render.py` | render_clip's RTL-stack check never supplies the 'linked libraries' evidence it claims to check, so the docume | 2/3 |
| major | `render.py` | render_clip() never runs the ldd/linked-library half of the §4.3.2 RTL-stack check the code itself defines | 2/3 |

## The pattern, again

Every blocker is the same class the previous external audit found: **a check that accepts the
shape of an answer without checking its content.** What makes it worth recording is that the
pattern reappeared *in the code written to fix it*:

- `_strict_bool` was added so `"false"` could not deserialize as `True` — then invariant #2's
  universal gate kept using plain truthiness, and the Gemini adapter used `bool()`.
- The gate was taught that an exit code is not evidence — then accepted a report in which
  every test skipped.
- `TranscriptStore.write_raw` was given `O_EXCL` so a path could not be attacker-chosen — and
  the credentials module two files away wrote a plaintext key through a symlink into a tracked
  file.
- `assert_rtl_stack` was given a second evidence source so a build could not certify itself on
  a flag alone — and the render path passed `""` for that second source, making it dead code.

The lesson is not "be more careful". It is that a guard added at one call site is not a guard,
and the only way to find that out is to have someone else look.

## What this review did not cover

- **Anything requiring the models.** No ASR has ever run, so §4.2 alignment, §4.1 normalization
  and the §2 index remain untested against real OmniASR output.
- **Real Kurdish footage.** Stage 0 is verified against one 4-second synthetic fixture.
- **The prompts themselves.** Whether the Kurdish judge's instructions actually elicit good
  editorial judgment is an §8.2 question needing the labelled set.
- **Concurrency.** Nothing was tested under parallel pipeline runs over the same work directory.

## Reproduce

Fixes and their regression tests: `tests/test_review_findings.py`. Each test fails against the
code as it stood before this review.


---

# Round 2 — 2026-08-07

Same method, different target: rather than re-reading the code, five reviewers attacked **the
eleven round-1 fixes** on their own terms, and a sixth worked the areas round 1 admitted it
never covered. 11 proposed, 8 survived, 3 blockers.

## The finding that matters

**Four of the eleven round-1 fixes introduced a new instance of the same bug class, one call
site over from where the fix landed.**

| Round-1 fix | What it introduced |
|---|---|
| `O_NOFOLLOW` rejects a symlinked `.env` | a **hardlinked** `.env` still rewrote a tracked file — O_NOFOLLOW checks the final component's *name*, never the inode's identity |
| `_strict_bool` in the live-response parser | `JudgeVerdict.from_dict`, the sibling path, took `"false"` unchecked all the way into a shipped `Editorial` |
| `assert_contiguous` refuses skipped sentences | it checks *index* contiguity; the clip is cut in **time**, and an out-of-time-order transcript still swallowed un-captioned speech |
| `O_EXCL` stops two writers clobbering raw | it made the *name* appear before the *content*, so a concurrent reader hit `JSONDecodeError` instead of an orderly refusal |

The pattern is not a bug. It is a habit: fix X at site A, never look at site B.

## And one more, in the fix for the fix

The first hardlink fix checked `st_nlink` *after* opening with `O_TRUNC` — which empties the
file at open time. The guard fired only once the tracked file it protected had already been
destroyed. Corrected: open without `O_TRUNC`, establish identity, then `ftruncate`.

A check in the wrong *place* is the same failure as a check of the wrong *thing*.

## Verdict

Every round-1 fix stops the literal exploit reported. None of them generalised without being
made to. The honest reading is that this codebase's invariants are enforced *at the sites
someone thought to look at*, and the only reliable way to find the others is an adversarial
reader who was not the author.
