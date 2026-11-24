```yaml
commit: 78b62f249bf1fe0c23bf462b14fdfbef7644d643
media_sha256: bbc2acc40bb9f69a0e1fc31b7fadc7353e628eae8acd9d69638fcda513fd95a2
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.smoke --yes --video D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4
```

# A5 Live Judge Smoke & Stage 4 Verdict on `gemini-4-carbon` (2026-11-19)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, `ffmpeg version 8.1.1-full_build-www.gyan.dev`
- **Git base commit (pre-edit HEAD):** `78b62f249bf1fe0c23bf462b14fdfbef7644d643` (with `D-339` working-tree update `KURDISH_EDITORIAL_JUDGE = "gemini-4-carbon"`, `JUDGE_SHADOW = "gemini-4-argon"`)
- **Credential:** `GEMINI_API_KEY: …IEu4` (`C:\Users\Wareen\AppData\Roaming\hawedit\credentials.env`, paid tier active; raw secret never printed)
- **Video:** `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4` (`298,767,645` B, SHA-256 `bbc2acc40bb9f69a0e1fc31b7fadc7353e628eae8acd9d69638fcda513fd95a2`)

## 1. Live `hawedit.smoke --yes` (Stage 3 Path A on Built-In 13.0 s `SAMPLE`)

- **Command:** `.venv\Scripts\python.exe -m hawedit.smoke --yes --video D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
- **Model:** `gemini-4-carbon` (`PathADiscovery`, `k=5`)
- **Measured wall time:** `44.860 s` (exit `1`)
- **Provider count:** `1,498` tokens (`~0.0030 USD` at `$2.00/1M` input tier through Nov 30, 2026)
- **Result:** All `countTokens` and K=5 `generateContent` requests succeeded (HTTP `200`). The model returned `0` candidates (`the judge found no candidates in this sample`) because `SAMPLE` spans `13.0 s` while Path A instructs `30..90 s` (`MIN_CANDIDATE_SPAN_MS = 30_000`), leaving Stage 4 unreached in `smoke.main`.

## 2. Live Stage 4 `GeminiJudge.judge_with_count` (20 Real Keyframes, `0..35,000 ms`)

- **Request:** `candidate_id="smoke-stage4-carbon"`, `InputMode.STAGE_4_TRANSCRIPT_FIRST`, `clip_in_ms=0`, `clip_out_ms=35000`, `20` real JPEG keyframes extracted from `zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
- **Model:** `gemini-4-carbon`
- **Measured wall time:** `18.469 s`
- **Provider token count & estimate:** `23,520` tokens, `est_usd=0.047040`
- **Validated structured output (`JudgeVerdict`):**
  - `hook_score`: `0.55` (`hook_type`: `"claim"`)
  - `self_contained`: `True`
  - `payoff_at_ms`: `32375`, `payoff_strength`: `0.58`, `ends_on_a_beat`: `True`
  - `meaning_fidelity`: `0.92`, `misleading_edit_risk`: `0.05`, `cultural_landing`: `0.85`
  - `narrative_role`: `"setup"`
  - `title_ckb`: `"داهاتووی ڕۆژنامەوانی و ژیریی دەستکرد لە هەولێر"`
  - `hashtags_ckb`: `["ڕۆژنامەوانی", "هەولێر", "ژیریی_دەستکرد", "میدیا", "کوردستان", "تەکنەلۆژیا"]`
  - `reason_ckb` confirmed grounded Sorani response referencing keyframes (`...پێش ئەوەی میواندارەکە قسە بکات.`).
