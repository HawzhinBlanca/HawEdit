# Plan — Content-Aware 10/10 Short-From-Long Program

Approved-by: Hawa (explicit prompt 2026-11-20: "do a deep research and make sure our result video is better than openshorts and opusclip, and we are really ready for making cintent, short from long, really pro, and set a research grade plan to make it content aware real 10/10, then using swarm implement all whn u sure")

## Architecture & Swarm Lane Partition (Zero File Collisions)

Four parallel implementation lanes branched from `gemini/number-one`, merged in strict order `Lane A -> Lane B -> Lane C -> Lane D` via `--no-ff` merge commits by the lead, followed by full gate verification and real multi-genre production (`ai` + `cooking`):

| Lane | Branch / Worktree | ADR | Owned Files (Exclusive) | Targeted Tests |
| --- | --- | --- | --- | --- |
| **Lane A** (`c10-discovery`) | `gemini/c10-lane-a` (`..\HawEdit-c10-lane-a`) | `D-356` | `src/hawedit/audio_signals.py`, `src/hawedit/topic_segmenter.py`, `src/hawedit/path_a.py`, `tests/test_c10_multimodal_discovery.py` | `test_c10_multimodal_discovery.py`, `test_path_a.py`, `test_topic_segmenter.py` |
| **Lane B** (`c10-reframe`) | `gemini/c10-lane-b` (`..\HawEdit-c10-lane-b`) | `D-357` | `src/hawedit/reframe.py`, `src/hawedit/render.py`, `tests/test_c10_reframe_anything.py` | `test_c10_reframe_anything.py`, `test_reframe.py`, `test_render.py`, `test_broadcast_studio.py` |
| **Lane C** (`c10-captions`) | `gemini/c10-lane-c` (`..\HawEdit-c10-lane-c`) | `D-358` | `src/hawedit/caption_polish.py`, `src/hawedit/silence.py`, `tests/test_c10_caption_polish_and_silence.py` | `test_c10_caption_polish_and_silence.py`, `test_silence.py`, `test_edit_plan.py` |
| **Lane D** (`c10-integrate`) | `gemini/c10-lane-d` (`..\HawEdit-c10-lane-d`) — branched AFTER A+B+C merge! | `D-359` | `src/hawedit/pipeline.py`, `src/hawedit/measure.py`, `tests/test_c10_pipeline_integration.py` | `test_c10_pipeline_integration.py`, `test_measure.py`, `test_pipeline.py`, `test_a2_one_command_reels.py` |

## Shared-Resource & Anti-Cheat Rules
- Lanes run `bash scripts/verify.sh --fast` + targeted pytest ONLY. Lanes NEVER touch `DECISIONS.md` (lead adds `D-356..D-359` cleanly on `gemini/number-one` to avoid merge conflicts), NEVER touch `scripts/*.floor`, NEVER touch `security/wsl-asr-vex.json` (lead re-pins VEX cleanly after each merge), NEVER touch `C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit` (`fix/kurdish-rtl-captions`, PR #25) or `D:\HawEdit-media\sources\`.
- Only the lead runs full `scripts/verify.sh` / `scripts/update-ledger.sh` gates on `gemini/number-one` and GPU jobs on HawaPC01 (GPU 0 NVENC transcode/encode, GPU 1 WSL OmniASR v12 + CTC-3B with `MAINTENANCE` lock and `:8000/:8001` HTTP `200` restoration).

## Real Multi-Genre Verification Plan (Post-Merge)
1. **Episode 1 (`ai`, `RO1PmSoqmCM` 1440p):** Re-run with `--topic-candidates --eased-push --encoder auto --polish-captions --silence-threshold-ms 1100 --silence-target-gap-ms 300 --judge-top-n 45 --max-clips 10` (Stage 0/1 cached), verify NVENC speedup, `double_cuts == 0`, `broadcast_scorecard.all_passed == True`, polished Sorani captions (zero `تۆپ تۆپ تۆپ` / `چیت سکۆدس`), and visually inspect every contact sheet + 4×4 grid.
2. **Episode 2 (`cooking`, `k_jxP903t5w`, 67 min, 17 gold teaser spans):** Derive 1440p H.264 on GPU 0 NVENC into `D:\HawEdit-media\excerpts\`, run full end-to-end pipeline (GPU 1 OmniASR v12 + CTC-3B with `MAINTENANCE` lock & `:8000/:8001` health restore) into `D:\HawEdit-media\reels\run-2026-11-20-cooking-reels\`, measure real teaser-overlap precision/recall against `evidence/teaser-gold-timestamps.md`, and visually inspect all delivered contact sheets (verifying both talking-head AND non-face cooking shots!).
3. Commit `evidence/content-aware-10-of-10-2026-11-20.md`, run final full `scripts/update-ledger.sh` gate on `gemini/number-one`, commit ratcheted floors cleanly, leave `git status` clean (not pushed).
