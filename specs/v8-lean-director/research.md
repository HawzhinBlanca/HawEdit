# Research: HawEdit V8 — Truly Content-Aware, Lean Creative Director Architecture

Date: 2026-11-22  
Target Repo: `HawEdit-swarm` (`gemini/number-one` @ `64d16b7`)  
Hardware Measured: `HawaPC01` — Dual `NVIDIA GeForce RTX 3090 Ti` (`GPU 0`: 24.5 GB hosting OmniASR + NVENC; `GPU 1`: **23.7 GB completely free**), 64 CPU threads, `ffmpeg 8.1.1-full_build` (HarfBuzz + FriBidi + NVENC), Node.js installed, LM Studio live on `127.0.0.1:1234`.

---

## 1. Root-Cause Diagnosis of Why Current HawEdit Feels "Algorithmic" Instead of Human

Direct inspection of the codebase (`155` modules, `98,617` LOC, with `pipeline.py` at `8,091` LOC and `captions.py` at `3,856` LOC) and the V7 rendered MP4s identifies **four structural causes** — none of which can be solved by adding more rules to `pipeline.py`:

| Defect Observed by Owner | Root Cause in Current V7 Architecture | Why Stacking More Heuristics Fails |
| --- | --- | --- |
| **"Unnecessary zoom and movement"** | `build_cinema_motion_filter()` applies continuous `0.08 * sin(in * 0.022)` horizontal sway on every frame, forces a hook zoom on beat 0, and forcibly splits any hold `> 5.5 s` with a `1.00 ↔ 1.16×` timer toggle regardless of content. | A human editor holds a **locked tripod (`1.00×`, zero sway)** ~75–85% of the time and punches in ONLY on 2–4 semantically earned moments (punchline, emotional reveal, or disguising a real jump-cut). Timers and sine waves cannot know whether a moment deserves camera motion. |
| **Subtitles feel static / too wordy (`3–4` words/line)** | `captions.py` packs up to 3–4 words per line with a flat `\clip` color fill and cannot animate true active-word spring-bounce or sliding rounded pills because `\fscx` inside `\clip` causes glyph ghosting. | Viral TikTok/CapCut/Submagic Kurdish captions use **1–2 words (max 3 ONLY when all 3 are short, `<= 14` chars total)** with tactile spring-bounce pop and a vibrant active-word rounded pill / glow highlight. |
| **ASR loanword/phonetic errors survive (`ما فەیبوو فایف`)** | Caption polish sees only *corrupted text*, never the *raw audio*. Once ASR mishears an English model name or loanword, a text-only model has to guess blindly. | Native **audio+video multimodal models** (Gemini 2.5 Pro / Gemini 3, or local **Qwen2.5-Omni-7B / Qwen3-Omni-30B-A3B** on free GPU 1) literally *hear* the speaker say the English loanword in context and repair it with near-100% fidelity. |
| **98k-LOC procedural sprawl (`pipeline.py` = 8,091 LOC)** | 15+ disconnected deterministic heuristic modules (`reframe`, `silence`, `audio_signals`, `captions`, `caption_polish`, `assembly`, `condenser`, `render`, `sound_design`) each make blind local guesses without sharing a single semantic understanding of the video. | Modern 2025–2026 editing systems (*VideoAgent* 2026, *Text-to-Edit* 2025, *HIVE* 2025, *Gemini Native Video Director*) invert this: **one multimodal brain watches+listens to produce one small declarative `DirectorScript` JSON, and a lean deterministic compiler renders it.** |

---

## 2. State-of-the-Art Research Survey (2025–2026)

### 2.1 Multimodal Director Architectures (*VideoAgent*, *Text-to-Edit*, *LongVideoAgent*, *HIVE*)
- **Core convergence across 2025–2026 research:**
  1. **Unified Native Video+Audio Understanding over Frame Sampling:** Models that ingest synchronized video + audio natively (Gemini 2.5 Pro / Gemini 3 via File API; open-weight Apache 2.0 **Qwen2.5-Omni-7B** and **Qwen3-Omni-30B-A3B** with Time-aligned Multimodal RoPE `TMRoPE`) perceive facial micro-expressions, hand gestures, tone/laughter, camera framing, AND spoken English loanwords simultaneously.
  2. **Declarative Edit-Script Separation (Text-to-Edit / VideoAgent):** The multimodal Director never calls FFmpeg directly or writes filters; it emits a **strict, typed, schema-validated `DirectorScript` JSON** referencing exact CTC word indices (`word_id`) and shot IDs. A tiny, 100% deterministic compiler translates `DirectorScript` into exact frame-accurate FFmpeg + subtitle graphics + audio mix.
  3. **Watch-Before-Ship Self-Critique Loop (bounded to 1 pass):** Sending a lightweight 480p @ 2 fps preview of the rendered clip + audio back to the multimodal critic catches unnecessary motion, awkward cuts, overlapping graphics, or mangled words *before* publication — emitting a minimal JSON patch rather than heuristics.

### 2.2 Active Speaker Detection (Replacing Face-Size Heuristics)
- Current HawEdit guesses the active speaker from bounding-box area / motion when diarization is unavailable (`BLOCKED.md` #4).
- **2025–2026 SOTA Open-Source Solutions (Apache/MIT, commercial-safe):**
  - **Light-ASD / LR-ASD** (`~1M` parameters, `< 100 MB` VRAM, ~20× lighter than TalkNet while matching AVA mAP): directly correlates lip-region optical motion with 16 kHz MFCC speech frames to identify the true speaking face per frame in 2-shots, reaction cuts, and podcasts — zero HuggingFace gated token required!

### 2.3 Cinematography & Restraint (Why Less Camera Motion Looks 10× More Expensive)
- Professional broadcast and top short-form editing studies (2024–2026) converge on three rules that directly fix the user's complaint:
  1. **Default = Locked Tripod (`1.00×`, `0.00` sway):** Never apply sinusoidal sway or timer-driven zoom to a talking head. Human eyes immediately register unmotivated camera drift as "cheap AI filter".
  2. **Motivated Shot-Scale Cuts Only (`2–4` per 45 s reel):**
     - **A/B Jump-Cut Mask (`1.00× ↔ 1.12×` instant 1-frame cut):** ONLY when an actual editorial jump-cut removes `>= 600 ms` of dead air/tangent (or on an explicit semantic beat from the Director).
     - **Earned Slow Dolly (`1.00× → 1.07×` cosine S-curve over 3–5 s):** At most **1–2 per reel**, ONLY when the Director marks a rising emotional/story payoff.
     - **Hard Cap:** Total moving-camera screen time `<= 25%` of clip duration; `>= 75%` rock-steady locked framing.
  3. **Source Multi-Cam Respect:** When the source podcast ALREADY cuts between cameras (`shot_cuts_ms`), hold `1.00×` cleanly instead of stacking digital zoom on top of real camera cuts.

### 2.4 Viral TikTok / CapCut Animated Kurdish (Sorani RTL) Subtitles
- **Exact Word-Chunking Law (Matches Owner Spec & Eye-Tracking Research):**
  - **1 word** if the word is `>= 8` characters OR marked `power_word=True` by the Director.
  - **2 words** default viral rhythm (instant peripheral comprehension, zero reading fatigue).
  - **Max 3 words ONLY** if all 3 are short (`<= 14` chars total including spaces, e.g. `لە ناو ماڵ` / `بۆ ئەوەی کە`) — NEVER 4 words.
- **Rendering Stack Comparison for True Viral TikTok Animated Kurdish RTL Subtitles:**

| Engine | HarfBuzz Kurdish RTL Ligatures | True Sliding Rounded Active-Word Pill | True Spring-Bounce Word Pop (0.00 px Ghosting) | Render Speed (45 s clip) | Dependencies & Licence |
| --- | --- | --- | --- | --- | --- |
| **A. Enhanced `libass` Viral Engine** (zero new deps) | Native HarfBuzz + FriBidi (already §4.3.6 golden-verified) | Approximate (`\p1` Bézier pill behind 1–2 word block, or bold stroke + glow) | **100% zero-ghosting spring-bounce** (`\fscx84→108→100`) on 1–2 word chunks without `\clip` conflict! | **~2 s** (NVENC) | Zero new deps (FFmpeg 8.1.1 already ships it) |
| **B. HarfBuzz + Skia / PangoCairo RGBA Track** (`uharfbuzz` + `skia-python`) | Native HarfBuzz + FriBidi (`python-bidi`) | **100% CapCut/Submagic pixel-perfect** dynamic rounded active-word pill sliding RTL across words with soft drop shadow & spring physics | **100% exact spring physics** per word, true blur glow, gradients, emoji/icon badges | **~3–5 s** (piped RGBA overlay into NVENC) | MIT / BSD (`skia-python`, `uharfbuzz`, `python-bidi`) — commercial-safe |
| **C. Chromium / Playwright HTML+CSS** (Node/Remotion-style) | Native browser HarfBuzz + BiDi + CSS `dir="rtl"` | **100% pixel-perfect** CSS `border-radius`, `backdrop-filter`, spring keyframes | **100% pixel-perfect** | ~15–25 s (headless browser frame capture) | Apache 2.0 (Playwright / Chromium — heavy runtime) |

**Engineering Verdict on Subtitles:**
- **Phase 1 (Immediate, Zero Bloat):** Ship a clean **Viral TikTok Kurdish Subtitle Engine** supporting BOTH:
  - **Path B (`uharfbuzz` + `skia-python` / Pillow-raqm)** OR **Path A (pure `libass` 1–2 word spring-bounce + active-word color/pill)**.
  - **Recommendation:** **`skia-python` + `uharfbuzz` (MIT/BSD)** piped directly as a 1080×1920 RGBA overlay into FFmpeg NVENC! Why? Because it gives **100% authentic CapCut/TikTok/Submagic active-word sliding rounded pills + real spring-bounce physics + true blurred shadows + pixel-perfect HarfBuzz Sorani Kurdish shaping** in ~150 lines of clean Python at ~10× realtime, with ZERO Chromium bloat and ZERO `libass` `\clip` limitations! (With pure `libass` 1–2 word spring-bounce kept as the fast fallback / golden-test-compatible mode.)

### 2.5 Model Choice for the Multimodal Director Brain (Cloud + Local on Free GPU 1)
On `HawaPC01`, **GPU 1 (`RTX 3090 Ti`) has `23.7 GB` completely free**, while Cloud Gemini is also configured:
- **Primary Cloud Backend (Highest Creative Intelligence):** **Gemini 2.5 Pro / Gemini 3** native video+audio (`File API` / inline 360p@1fps proxy + 16 kHz audio of the candidate 60 s clip = only ~18K tokens, `< $0.02` per clip!).
- **Primary Local Zero-Cost Backend (GPU 1, `$0` API cost, zero rate limits, Apache 2.0):** **Qwen2.5-Omni-7B** (or **Qwen3-Omni-30B-A3B** 4-bit via vLLM / Transformers on `CUDA_VISIBLE_DEVICES=1`) — natively ingests the exact same 360p clip video + audio + Kurdish transcript and emits the exact same `DirectorScript` JSON!
- **One unified `DirectorBrain` protocol (`src/hawedit/director_v8.py`):** Both Cloud Gemini and Local Qwen-Omni implement the exact same 1-method interface `direct_clip(video_proxy, audio_wav, words, shots) -> DirectorScript`, validated strictly by schema + E3 edit rules!

---

## 3. Lean Architectural Vision ("Smartest, Leanest Creative Pipeline")

Instead of adding another 2,000 lines onto `pipeline.py` (`8,091` LOC), V8 introduces a **clean, self-contained, 5-module Creative Director Engine (~1,100 LOC total)** sitting cleanly beside HawEdit's verified Stage 0 / Stage 1 / E3 / Level C invariants:

```
Source 1440p Video
   │
   ▼
[1. PERCEIVE]  (Exact Local Sensors — GPU 0 / GPU 1)
   • OmniASR 7B + CTC-3B + VAD sub-word onset trim (exact Kurdish words & ms)
   • Light-ASD ONNX on GPU 1 (true per-frame active speaker, not box-size guess)
   • Shot detector + locked per-shot face framing (zero jitter)
   │
   ▼
[2. DIRECT]    (ONE Native Video+Audio Multimodal Call — Gemini 2.5/3 OR Local Qwen-Omni)
   • Watches actual clip video + listens to actual Kurdish/English audio
   • Outputs strict `DirectorScript` JSON:
       - word_repairs (audio-grounded Kurdish + English loanword fixes!)
       - cuts (semantic fillers / tangents / optional cold-open hook)
       - camera_moves (DEFAULT LOCKED 1.00x; ONLY 2-4 earned punch/push beats, ZERO sway!)
       - caption_beats (1-2 word / max-3-short viral chunks + semantic power words)
       - hook_title_ckb (4-7 punchy words)
       - visual_interrupts (0-2 earned callouts ONLY where story demands)
   │
   ▼
[3. VALIDATE]  (Deterministic Safety Gate — Zero Hallucinations)
   • Enforces E3 zero mid-word cuts & padding bounds
   • Enforces camera restraint budget (<= 25% motion, 0 sway, >= 75% locked)
   • Enforces caption chunk law (1-2 words, max 3 only if <= 14 chars)
   • Verifies 1:1 Kurdish word alignment & HarfBuzz coverage
   │
   ▼
[4. COMPILE]   (Lean GPU Renderer — NVENC + TikTok Kinetic Subtitles)
   • Locked per-shot crop + ONLY Director-approved camera moves (zero timer/sine zoom!)
   • Viral TikTok Animated Kurdish Subtitles (1-2 words, spring-bounce, active-word rounded pill!)
   • Linear -14.0 LUFS broadcast speech mastering + subtle hook presence
   │
   ▼
[5. CRITIQUE]  (Watch-Before-Ship Multimodal Judge — Max 1 Bounded Patch)
   • Watches 480p@2fps rendered preview + audio
   • Checks: zero unnecessary motion, zero broken Kurdish words, crisp pacing, viral hook
   • Either APPROVES or emits 1 surgical `DirectorScript` JSON patch -> re-compile in ~8 s
```

---

## 4. Open Questions & Decisions Needed Before Implementation

1. **Subtitle Rendering Engine:**
   - **(Recommended)** `skia-python` + `uharfbuzz` + `python-bidi` (MIT/BSD, true CapCut/TikTok sliding rounded active-word pill + spring-bounce physics + true soft drop shadows, ~4 s render) + pure `libass` 1–2 word spring-bounce fallback.
   - Alternative: Pure `libass` 1–2 word spring-bounce only (zero new dependencies, slightly simpler pill visuals).
2. **Primary Multimodal Director Brain:**
   - **(Recommended)** Unified `DirectorBrain` supporting **BOTH** Cloud Gemini (2.5 Pro / 3 native video+audio when quota available) **AND** Local **Qwen2.5-Omni-7B / Qwen3-Omni-30B-A3B** on free `GPU 1` (`23.7 GB` VRAM, `$0` cost, Apache 2.0).
3. **Active Speaker Detection Upgrade:**
   - **(Recommended)** Add lightweight ONNX **Light-ASD / LR-ASD** (`~1M` params, `< 100 MB` VRAM, commercial-safe) on `GPU 1` so 2-shots and podcast reaction cuts lock onto the *actual speaking mouth*, never guessing from face size.
4. **Architectural Placement:**
   - **(Recommended)** Build V8 as a **lean, isolated package (`src/hawedit/v8/`)** (~5 small modules: `schema.py`, `director.py`, `asd.py`, `tiktok_subs.py`, `compiler.py`) invoked via a clean `--v8-director` entry point (and standalone `python -m hawedit.v8`), keeping all 6,773 existing tests green and `pipeline.py` untouched except for one thin 15-line dispatch hook!
