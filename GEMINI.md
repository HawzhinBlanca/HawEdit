# GEMINI.md

This file establishes operating instructions for Google Antigravity and Gemini CLI agents in HawEdit.

Operating rules are defined in `AGENTS.md` and `.agents/rules/strict-fail-stop.md`.

## Mandatory Operating Directives

1. **Strict Fail-Stop / Zero Silent Fallbacks**:
   - If ANY stage fails (ASR, forced alignment, face/speaker tracking, RTL shaping, boundary check, encoder probe, QC judge), the application MUST HALT immediately.
   - Never silently fall back (e.g. no fallback to static centre crop when face tracking was requested, no fallback to uniform word timing, no fallback to software encoder when NVENC was requested).

2. **Pro Kurdish Reel Quality Standards**:
   - Viral pacing: 30-55s duration, strong 0-3s hook, complete self-contained narrative.
   - Dynamic 9:16 vertical reframing with smoothed face/speaker tracking and upper-third eye placement.
   - High-energy word-by-word animated karaoke subtitles in Sorani Kurdish (`Noto Naskh Arabic` / `Vazirmatn`, `shaping=complex`, vibrant highlight, dark outline, safe bottom margin).
   - Dynamic punch-in zoom (1.10x-1.20x) on key emphasis points.

3. **Follow `AGENTS.md` Workflows**:
   - Research before coding, plan, test-first implementation, verify with the gate.
