# Adversarial production hardening — 2026-08-09

This note records failures reproduced after the end-to-end pipeline first went green. It is
implementation evidence, not a model-quality benchmark.

## Reproduced failures

- `Qc(auto_pass=True, human_reviewed=False)` cleared `Clip.assert_renderable()` and could reach
  Stage 6 despite the documented always-human gate.
- Hosted model JSON booleans were coerced into numeric authority: Gemini scores and payoff,
  Path A spans/scores, TimeLens `[[false,true]]`, and `totalTokens=true` all became usable values.
- Reused frame directories promoted stale pixels: 5 new + 15 old Stage 4 JPEGs, and 6 new + 14
  old shared visual frames, passed the previous aggregate-count checks.
- `assert_encoded_span(100000, 2000, 40)` succeeded, allowing unreviewed trailing footage to be
  published.
- A controlled transcript writer pause exposed `digest_exists=True/raw_exists=False`; the losing
  pipeline writer could catch the immutable refusal and immediately hit `FileNotFoundError`.
- `PathBError` and `VideoInputError` escaped `run_pipeline` instead of producing the promised
  skipped-stage report.

## Enforced boundaries

- Human review is mandatory independently of automatic QC.
- Model numbers use exact JSON types, reject booleans/strings/non-finite values, and token counts
  are non-negative integers.
- Each ffmpeg call owns a unique output namespace; only its outputs can be returned.
- Encoded duration has a one-frame tolerance in both directions.
- Transcript publication/read/verification is serialized per media id across threads and
  processes; orphan write-once evidence fails closed.
- Known visual component-domain failures—including backend `RuntimeError`/`OSError` and ffmpeg
  launch refusal—are normalized at their adapter/composer boundary while unknown exceptions
  remain visible as programming errors.

## Executable controls

The regressions live in:

- `tests/test_clip.py`, `tests/test_render.py`
- `tests/test_gemini.py`, `tests/test_judge.py`, `tests/test_path_a.py`,
  `tests/test_video_grounding.py`
- `tests/test_keyframes.py`, `tests/test_video_input.py`
- `tests/test_transcripts.py`
- `tests/test_qwen_visual.py`, `tests/test_video_reader.py`, `tests/test_visual_pipeline.py`,
  `tests/test_pipeline.py`

The combined local canonical gate passed 1,417/1,417 with zero skips, plus Ruff, formatting and
mypy across 102 source files. The exact-SHA remote run is recorded only after commit and is the
promotion evidence; this local count is a development control, not a substitute for it.
