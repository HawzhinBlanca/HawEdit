# Eight modules had no status, and four documents described code that refuses

> Measured 2026-08-08 on hawapc01, `transformers` 4.57.6, `cuda:0`, against `3f3ace4`.

An external review reported that four modules — `visual_pipeline.py`, `keyframes.py`,
`reframe.py`, `editorial_bench.py` — had "no PROGRESS ledger row at all," and that three
documents claimed short media keeps every scene while the code refuses it. Both reproduce. The
count was low: **eight** modules had no status, not four.

## What the ledger was actually missing

`tests/test_claims.py::test_the_module_map_covers_every_module` has bound the README's module
map to the filesystem for some time, and it passes — every module is in the README. PROGRESS.md
had no equivalent, so the ledger drifted where the README could not.

```
$ for f in src/hawedit/*.py; do grep -q "$(basename $f)" PROGRESS.md || echo "UNLISTED $f"; done
UNLISTED asr_worker.py         104 lines
UNLISTED collisions.py         135 lines
UNLISTED editorial_bench.py    213 lines
UNLISTED gate.py               ← found only by the new test; the row cited its *test*
UNLISTED keyframes.py           78 lines
UNLISTED reframe.py            102 lines
UNLISTED smoke.py              198 lines
UNLISTED visual_pipeline.py    209 lines
UNLISTED wsl_setup.py          173 lines
```

**Two of them were described, and that is the more interesting failure.** `visual_pipeline.py`
and `reframe.py` each had a paragraph — as a `>` blockquote *after* the table, naming neither
the file nor a status mark. So the composition that the §9 M5 row calls "DONE in code" was not
itself counted in the 35 DONE / 7 PARTIAL tally, and no test could reach it, because a test that
greps the file would have passed on the prose. The review's phrase "no ledger row" was right
about the status and wrong about the description; the distinction is why the new test reads the
**evidence cell of a row whose status cell is a legend mark**, not the document.

`gate.py` is the case nobody spotted from either side: M0.1 cited `tests/test_gate.py` and never
the module it tests.

## The four modules, measured rather than inferred

Run: `python probe_four.py` against `tests/fixtures/kurdish-speech-3cuts.mp4` (4162 ms, cuts at
1400/2800 ms).

### `keyframes.py` — real bytes, right span

```
frames returned: 6
  t=  347 ms  bytes=  3332  SOI=FFD8  image/jpeg
  t= 1040 ms  bytes=  3332  SOI=FFD8  image/jpeg
  t= 1734 ms  bytes=  2624  SOI=FFD8  image/jpeg
  t= 2428 ms  bytes=  2624  SOI=FFD8  image/jpeg
  t= 3122 ms  bytes=  3424  SOI=FFD8  image/jpeg
  t= 3815 ms  bytes=  3424  SOI=FFD8  image/jpeg
distinct timestamps: 6 of 6
distinct payloads:   3 of 6
```

Six real JPEGs (`FFD8` start-of-image), six distinct stamps 693–694 ms apart, every one inside
the requested `0..4162 ms`. **Three distinct payloads is correct, not a defect** — the fixture is
three static shots, so two frames sampled inside one shot are byte-identical pixels. Worth
recording because it is exactly the shape a broken sampler would also produce, and the
discriminator is the timestamps, which are all distinct.

### `reframe.py` — the fallback runs on real pixels; the tracked path does not

```
focus points: 0
  -> empty: render_clip labels the crop Reframe.STATIC_CENTRE
```

Correct: the fixture is coloured digits and contains no face. So `Reframe.FACE_TRACKED` is
unexercised on real footage, and the honest claim is that the *refusal to claim tracking* is
verified, not the tracking.

This also dates a stale cell. M3.3's shortfall read *"the crop is static and says so by name,
`Reframe.STATIC_CENTRE`, never `SPEAKER_TRACKED`"* — a two-value description of a three-value
enum, written before `reframe.py` existed and left standing after `FACE_TRACKED` was added and
selected by `render_clip`.

### `editorial_bench.py` — the harness exists, the labels do not

```
MIN_REGRESSION_ITEMS = 20
labelled sets on disk: 0 []
  refused empty set:   ValueError: editorial set has 0 items; the promotion floor is 20
  refused interim set: ValueError: an interim editorial set cannot be reported as production evidence
```

Both refusals matter: the harness cannot be made to print a number it did not measure. Note the
two floors answer different questions — `MIN_REGRESSION_ITEMS = 20` is §3's bar for *promoting a
judge model*, M7.2's 200–500 is §8.2's bar for *tuning thresholds*. Clearing the first would not
close M7.2, and conflating them would be an easy way to claim the eval set exists.

### `visual_pipeline.py` — composed, and refused by its own floor on the only media here

```
probe: duration_ms=4162 cuts=(1400, 2800)
planned windows: 3
  kurdish-speech-3cuts:s0:w0  0..1400 ms
  kurdish-speech-3cuts:s1:w0  1400..2800 ms
  kurdish-speech-3cuts:s2:w0  2800..4162 ms
REFUSED: VisualPipelineError
  visual retrieval refused this media: the index holds 3 windows and 7 survivors were asked
  for. §3 Stage 2 fixes the count at 5–10 …
peak VRAM: 4.08 GiB
```

The real `QwenVisualEmbedder` embedded all three windows on `cuda:0` and the composed path then
refused, correctly. The reader factory in this probe raises if constructed; it never was.

**4.08 GiB is the load-bearing number.** `evidence/m5-2-reranker.md` records 8.16–8.17 GiB with
embedder and reranker both resident. Half of that here means the reranker's weights never
loaded — which is D-066's claim ("moved before the reranker runs so a too-short media costs no
GPU time") measured rather than asserted. The floor is ahead of the *weights*, not merely ahead
of the call.

The consequence for the ledger: M5.5's happy path is unexercised on real media in this checkout,
and needs media with ≥5 scenes (`BLOCKED.md` #1).

## The document contradictions

| Where | Said | Code |
|---|---|---|
| `README.md` Stage 2 row | "or all scenes on shorter media" | `visual_index.py:500` raises |
| `AUDIT_REPORT.md` | "Short media keeps all available scenes" | same |
| `PROGRESS.md` M5.3 | "`run_pipeline(..., read_scenes=…)` makes the union two-sided" | `pipeline.py:618` raises on any non-`None` |
| `README.md` gate section | floor is "tests **collected**" | `gate.py:162` compares `evidence.passed` |
| `AUDIT_REPORT.md` | "1,063 collected, 1,063 passed" | floor was 1,068 |
| `PROGRESS.md` M3.3 | enum has two values | `render.py` has three |

The `read_scenes` correction did exist — eight lines below the row, in the same class of floating
blockquote as the two missing modules. The row itself still advertised a removed API, which is
the failure mode of recording corrections as footnotes rather than in the cell.

`collected` vs `passed` is the one with teeth: the two differ by exactly the skips, so a README
promising a floor on *collected* tests describes a ratchet that a creeping skip slides straight
through — the precise failure `verify.sh` was built against.

## The wheel hash, which was not on the review's list

The review quoted a current wheel as `309,535 bytes, SHA-256 3BB56324…` and faulted
`AUDIT_REPORT.md` for holding an obsolete hash. Measured, two consecutive builds at one
unchanged commit:

```
$ pip wheel --no-deps -w $TEMP/whl_rc  .   → 309,536 bytes  89CA7434E9F60D00…
$ pip wheel --no-deps -w $TEMP/whl_rc2 .   → 309,536 bytes  A77FEEA01C18C93F…
```

Same size, **different digest**. Nothing sets `SOURCE_DATE_EPOCH`, so ZIP entries carry build
mtimes. Every wheel hash this project has ever recorded was obsolete the moment it was written,
including the one the review offered as current — so the audit's figure was not stale, it was
never meaningful. `AUDIT_REPORT.md` now records the size and states why no digest is quoted.

## Mutation audit, against a baseline verified green first

Baseline `VERIFY OK — 1072 passed, 0 skipped` before mutating.

```
baseline: GREEN
CAUGHT  the M5.5 row stops naming visual_pipeline.py
CAUGHT  visual_pipeline.py named ONLY in a prose block, not in a status row
CAUGHT  README promises short media keeps every scene
CAUGHT  README calls the floor a count of tests collected
CAUGHT  the audit quotes a test count with no date

5/5
```

The second is the control that matters. It reintroduces the *original* failure — the module
described in prose with no status — and confirms the test measures presence-in-the-tally rather
than presence-in-the-file. Without it the first mutation alone would be satisfied by a test that
greps the whole document, which is the test I would otherwise have written.

## One test was redesigned mid-audit, and the reason is worth keeping

The audit-count test first asserted the figure *equalled* `scripts/test-count.floor`. It went
red at baseline — because adding these four tests ratcheted the floor to 1,072 and the audit
said 1,068. That is a test that fails whenever anyone adds a test, and its only cheap fixes are
editing a historical document or deleting the check: manufactured pressure to weaken the gate,
which the project's own rules forbid.

It also misdescribed the defect. `1,063` was not wrong because it differed from today's floor;
it was wrong because nothing on the line said *when* it was true. The test now requires a date
beside any test count in the audit and lets the number age, which is what a measurement in a
dated report is supposed to do.
