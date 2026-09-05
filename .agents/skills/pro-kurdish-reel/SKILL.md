---
name: pro-kurdish-reel
description: >-
  Runs long podcasts and interviews through the HawEdit pipeline to generate viral,
  high-retention 9:16 Kurdish social reels with smart reframing, consistent subject tracking,
  dynamic cuts/zooms, animated karaoke subtitles, and strict fail-stop validation (zero fallbacks).
---

# Pro Kurdish Reel Generation Skill

This skill provides the comprehensive runbook to repurpose long-form Kurdish (Sorani/`ckb`) videos and podcasts into captivating, viral, social-media-ready 9:16 vertical reels (Instagram Reels, TikTok, YouTube Shorts).

## Core Quality Directives & Reality Check Rules

1. **True Kurdish Understanding & Zero Dead Air**:
   - Never clip mid-sentence or mid-thought (Kurdish Invariant #2).
   - Filter out long multi-second pauses (> 1.5s silence gaps) between sentences by selecting tightly connected Q&A pairs or continuous insight segments.
   - Immediate 0–3s hook with strong narrative payoff within 20–55s.

2. **Viral Subtitle Engine (RTL Popups & Word Highlighting — D-269)**:
   - **Never render multi-line paragraph walls of text** on screen simultaneously.
   - **Avoid inline `\kf` tags in Kurdish**: `libass` places inline override runs in Left-to-Right order (libass issue #406), inverting Kurdish word order on screen and sweeping LTR.
   - **Mode A: Kinetic Viral Popups (`CaptionStyle.VIRAL_POPUP`)**:
     - 1 to 2 words per popup event (max ~18 characters or ~1.5s duration).
     - Formatted as a single unbroken RTL string with zero internal tags, natively shaped by HarfBuzz.
     - Micro-bounce elastic scale animation at onset: `{\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)}`.
     - Active word: Vibrant **Electric Gold / Neon Yellow** (`&H0000E5FF`).
     - Outline: `4.5px` solid black border + `2.0px` drop shadow.
     - Typography: `Noto Naskh Arabic` / `Vazirmatn` Bold (`74-108pt`).
   - **Mode B: True RTL Word Highlighting (`CaptionStyle.RTL_WORD_HIGHLIGHT`)**:
     - Uses HarfBuzz prefix measurements to position words with explicit `\pos(x, y)` tags.
     - Mathematically enforces $X(w_0) > X(w_1) > \dots > X(w_{n-1})$ so Word 0 is on the right and highlighting sweeps Right-to-Left.
     - Active word: Electric Gold (`&H0000E5FF`), inactive words: crisp White (`&H00FFFFFF`).
   - **Safe Margins**: `Alignment: 2` (bottom-center), `MarginV: 360` (clearing TikTok/Reels UI overlay buttons and captions bar).
   - **RTL Shaping**: Mandatory `shaping=complex` with HarfBuzz + FriBidi.

3. **Rock-Solid Dynamic Reframing (No 5Hz Micro-Jitter)**:
   - Do NOT use raw per-frame OpenCV bounding-box stairstep jumps (`if(lt(t))`).
   - Cluster camera positions per speaker segment (Host side vs Guest side).
   - Lock stable framing on the active speaker; cut cleanly on speaker turn.
   - Upper-third eye-level placement with natural headroom.

4. **Dynamic Pacing & Punch-in Zoom**:
   - Visual attention reset: Apply **1.12x–1.15x punch-in zoom** on key punchlines, revelations, or transitions every 3–6 seconds to maintain high viewer retention.

5. **STRICT FAIL-STOP POLICY (ALL STOP — ZERO SILENT FALLBACKS)**:
   - If ASR, forced alignment, face tracking, RTL shaping, sentence boundary, or encoder fails $\rightarrow$ **HALT IMMEDIATELY**.
   - No silent degradation to static center crop, no guessing word timings, no software encoder fallback when NVENC is requested.

---

## Pro Subtitle Configuration (ASS / Substation Alpha)

```ini
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kurdish,Noto Naskh Arabic,108,&H0000E5FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4.5,2,2,60,60,360,1
Style: KurdishDim,Noto Naskh Arabic,108,&H00FFFFFF,&H0000E5FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4.5,2,2,60,60,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
; 1-2 word kinetic popups or RTL-positioned word highlights (D-269)
```

---


## Failure Checklist (ALL STOP Conditions)

| Stage | Trigger Condition | Action |
|---|---|---|
| **ASR** | Missing transcript or CER > threshold | **STOP** — Never invent transcript |
| **Alignment** | Word timestamps missing or non-monotonic | **STOP** — Never guess word timings |
| **Reframe** | Face tracker returns 0 focus points | **STOP** — Never quietly fall back to center crop |
| **Captions** | Missing Kurdish glyphs or `shaping!=complex` | **STOP** — Never burn unshaped/broken text |
| **Boundary** | Sentence truncated or incomplete | **STOP** — Never render partial sentence |
| **Encoder** | Requested hardware encoder fails probe | **STOP** — Never silently substitute encoder |
| **QC** | Hook score < 0.75 or misleading risk > 0.05 | **STOP** — Never publish unapproved content |
