# Plan: HawEdit V8 — Lean Multimodal Content-Aware Director (`src/hawedit/v8/`)

Status: **APPROVED — Executing via V8 Swarm**  
Approved-by: Owner (2026-11-22) — Skia+HarfBuzz RGBA overlay (+ libass fallback), Dual Director (Local Qwen-Omni GPU 1 + Cloud Gemini), Lean 5-module `src/hawedit/v8/` + Light-ASD + Watch-Before-Ship critic.  
Based on: [research.md](file:///C:/Users/Wareen/.gemini/antigravity/scratch/HawEdit-swarm/specs/v8-lean-director/research.md)

---

## 1. Goal & Measurable Acceptance Criteria (EARS)

1. **Zero Unnecessary Camera Movement (`D-382`):**
   - WHEN compiling a `DirectorScript`, THE camera compiler SHALL hold `1.00×` locked framing with `0.00` sinusoidal horizontal sway on all unmarked beats, permit at most `4` Director-motivated camera moves per 60 s clip, and enforce `<= 25%` moving-camera time (`>= 75%` rock-steady locked tripod).
2. **Viral TikTok Animated Kurdish Subtitles (`D-383`):**
   - WHEN chunking Sorani words for viral subtitles, THE subtitle engine SHALL emit `1` word (for `>= 8`-char words or Director `power_word` beats), `2` words by default, and `3` words ONLY when all 3 fit within `<= 14` characters total — NEVER `4+` words — rendered with spring-bounce pop-in, vibrant active-word rounded pill / highlight, HarfBuzz RTL Kurdish shaping, and `0.00 px` glyph ghosting.
3. **Native Video+Audio Multimodal Director (`D-384`):**
   - WHEN directing a candidate clip, THE `DirectorBrain` SHALL ingest the actual clip video proxy + 16 kHz audio + word-indexed transcript (via Cloud Gemini native video+audio OR Local Qwen-Omni on GPU 1) and return a strictly schema-validated `DirectorScript` containing audio-grounded Kurdish/English `word_repairs`, semantic `cuts`, restrained `camera_moves`, `caption_beats`, `hook_title_ckb`, and optional `visual_interrupts`, failing loudly on malformed output with zero silent fallbacks.
4. **True Audio-Visual Active Speaker Tracking (`D-385`):**
   - WHEN multiple faces appear in a shot, THE `Light-ASD` module SHALL score per-face lip-to-audio synchronization and lock the 9:16 crop onto the true active speaker with hold-and-step shot cuts (zero mid-shot camera drift).
5. **Watch-Before-Ship Multimodal Self-Critique (`D-386`):**
   - WHEN a V8 clip finishes rendering, THE multimodal critic SHALL inspect the 480p@2fps rendered preview + audio for unnecessary camera motion, broken Kurdish captions, bad cuts, and subtitle legibility, applying at most 1 bounded `DirectorScript` JSON patch before final publication.
6. **Lean Isolation:**
   - ALL V8 logic SHALL live in 5 small modules under `src/hawedit/v8/` (`<= 1,500` LOC total) with ZERO bloat added to `pipeline.py` (only a thin CLI/module entrypoint) and ZERO regressions across all 6,773 existing tests.

---

## 2. Clean 5-Module Architecture (`src/hawedit/v8/`)

| Module | Responsibility | Approx LOC | Dependencies |
| --- | --- | --- | --- |
| `src/hawedit/v8/schema.py` | Strict frozen dataclasses (`DirectorScript`, `CameraMove`, `CaptionBeat`, `WordRepair`, `CutRegion`, `VisualInterrupt`, `CritiqueVerdict`) + deterministic validator enforcing E3 edit rules, `<= 25%` camera-motion budget, `0` sway, and `1–2` (max `3` short) word chunk law. | ~220 | stdlib only |
| `src/hawedit/v8/director.py` | Unified `DirectorBrain` protocol + `GeminiVideoDirector` (native video+audio) + `LocalOmniDirector` (Qwen2.5-Omni / Qwen3-Omni on GPU 1 via OpenAI/vLLM multimodal API) + `critique_rendered_clip()` watch-before-ship loop. | ~320 | stdlib `urllib` + existing `gemini.py` |
| `src/hawedit/v8/tiktok_subs.py` | Viral TikTok Kurdish RTL subtitle engine: strict `1 / 2 / max-3-short (<= 14 chars)` chunker + spring-bounce active-word rounded-pill renderer (`skia-python` + `uharfbuzz` + `python-bidi` RGBA overlay track, plus pure `libass` 1–2 word spring-bounce renderer). | ~350 | `uharfbuzz`, `skia-python`, `python-bidi` (MIT/BSD) or pure `libass` |
| `src/hawedit/v8/asd.py` | Lightweight ONNX `Light-ASD` / `LR-ASD` audio-visual active speaker scorer on GPU 1 / ONNXRuntime, feeding clean locked per-shot crops into `reframe.py`. | ~220 | `onnxruntime`, `cv2`, `numpy` (already installed) |
| `src/hawedit/v8/compiler.py` | Lean end-to-end V8 orchestrator (`python -m hawedit.v8`): Perceive → Direct → Validate → Compile (NVENC, locked camera + ONLY Director-earned moves, viral TikTok subs, `-14.0 LUFS` linear audio) → Watch-Before-Ship Critique. | ~300 | reuses existing `silence.py`, `render.py`, `edit_plan.py`, `delivery.py` |

---

## 3. Execution Phases (After Approval)

- **Phase 1 — Immediate Visual & Motion Breakthrough (Zero Cloud Dependency Required):**
  1. `schema.py` + `compiler.py` camera restraint (kill sinusoidal sway & 5.5 s timer zoom; locked `1.00×` tripod by default + ONLY 2–4 earned moves).
  2. `tiktok_subs.py` — true viral TikTok Kurdish animated subtitles (`1–2` words, max `3` only if `<= 14` chars, spring-bounce + vibrant rounded active-word pill, HarfBuzz RTL verified on real 1080p PNGs).
  3. Render & visually inspect real `AI s86-87`, `AI s19-22` (condensed), and `Cooking s7-7` side-by-side against V7!
- **Phase 2 — Multimodal Director Brain + Watch-Before-Ship Critic:**
  4. `director.py` — Native Video+Audio `DirectorBrain` (Cloud Gemini File API + Local Qwen2.5-Omni-7B / Qwen3-Omni on free GPU 1) actually watching+listening to fix English loanwords (`ما فەیبوو فایف`), select earned camera beats, and pick semantic power words + 1-pass Watch-Before-Ship critic.
- **Phase 3 — Active Speaker Detection (`Light-ASD`) & Full Gate:**
  5. `asd.py` — ONNX `Light-ASD` per-face active speaker detection for multi-person podcasts.
  6. ADRs `D-382`–`D-386`, VEX re-pin, multi-genre V8 evidence, full `bash scripts/verify.sh` green.
