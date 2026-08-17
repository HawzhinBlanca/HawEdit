# Research - bounded Stage 4 keyframe reads

Parent roadmap: `specs/true-10-10-acceptance/plan.md`, Phase 8.

Serena is not available in this Codex environment, so symbol and reference discovery used the
repository-native `rg` fallback required by `AGENTS.md`.

## Current behavior

- `JudgeFrame.__post_init__` in `src/hawedit/judge.py` refuses image payloads larger than 5 MiB
  and empty payloads.
- `_read_keyframe` in `src/hawedit/keyframes.py` calls `Path.read_bytes()`, so it reads an entire
  ffmpeg output into memory before `JudgeFrame` can enforce that limit.
- `extract_judge_frames` creates a unique owned directory and deletes it in `finally`; a
  `KeyframeError` raised while reading therefore retains the existing cleanup behavior.
- Empty extracted files reach `JudgeFrame` and raise `ValueError`. The pipeline normalizes
  `KeyframeError` for this operational adapter boundary, so an empty ffmpeg artifact currently
  bypasses the structured failure contract.

## References and callers

- Direct constructor consumers: `hawedit.gemini`, tests, and request construction in
  `hawedit.judge`.
- Extraction consumers: `hawedit.pipeline` and `hawedit.smoke`.
- Existing tests cover ffmpeg failure, read `OSError`, cleanup, timestamps, real JPEG bytes, and
  the post-read 5 MiB `JudgeFrame` ceiling. They do not prove that the file read itself is
  bounded or that an empty extracted file is normalized.

## Decision

Export one authoritative `MAX_JUDGE_FRAME_BYTES` constant from `hawedit.judge`. Make the
extractor read at most `limit + 1` bytes, refuse oversize and empty files as `KeyframeError`, and
leave direct `JudgeFrame` validation intact as defense in depth. This implements BLUEPRINT
section 3 Stage 4's bounded multimodal request without changing image count, quality, or provider
routing.
