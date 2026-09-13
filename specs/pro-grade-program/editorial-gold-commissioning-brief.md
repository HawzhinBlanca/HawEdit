# Editorial Gold Commissioning Brief & Human Evaluation Protocol (Phase C1)

> **Status:** Commissioning Brief Prepared — Awaiting Human Editor & Viewer Panel Commissioning by Hawa.
> **Dependency:** Tracked under `BLOCKED.md` #25.
> **Tooling:** Implemented in `src/hawedit/comparison_kit.py` and proven in `tests/test_comparison_kit.py`.

---

## 1. Executive Summary & Objective

In accordance with `specs/pro-grade-program/gemini-agent-prompt-2026-09-13.md` (Phase C1) and `BLUEPRINT.md`:
- **The Objective:** Create a high-fidelity ground truth dataset consisting of **20 diverse Kurdish long-form episodes** (podcasts, TV interviews, political debates, news segments) independently cut into viral 9:16 vertical short reels by a professional Kurdish video editor.
- **Human Panel:** 20 native Sorani Kurdish viewers to evaluate 200 blind pairwise comparisons between human editor cuts and HawEdit system renders.
- **Rule of Honesty:** The system ranker weights and the claim of parity/superiority cannot be self-certified or fitted on synthetic data. They must be fitted and verified on this empirical gold set.

---

## 2. Editor Commissioning Specifications (20 Episodes)

### 2.1 Episode Selection Requirements
The 20 episodes must span the linguistic and acoustic diversity defined in `BLUEPRINT.md` §8.1:
1. **Dialects:**
   - Hewlêr (Erbil) informal & formal (minimum 6 episodes)
   - Slemani (Sulaymaniyah) informal & formal (minimum 6 episodes)
   - Mukriyan / Mahabad formal & broadcast (minimum 3 episodes)
   - Mixed code-switching (Kurdish-English, Kurdish-Arabic) (minimum 5 episodes)
2. **Audio/Video Characteristics:**
   - Multi-speaker overlapping debate (minimum 4 episodes)
   - Solo monologue / formal presentation (minimum 4 episodes)
   - Studio two-shot interview (minimum 8 episodes)
   - Ambient/field audio with background noise (minimum 4 episodes)

### 2.2 Editorial Output Deliverables
For each episode, the professional Kurdish editor must deliver:
1. **1 to 3 Vertical Reels (9:16, 1080x1920, H.264/AAC, 30-55 seconds):**
   - Must represent the strongest, most compelling highlight moments of the episode.
   - Pacing: Tight, self-contained narrative with strong 0-3s hook and clear payoff.
   - Framing: Active speaker reframed to vertical with face in upper third.
   - Excision: Clean removal of long pauses and stumbles without unnatural speech cadence.
2. **Editorial Log (`editor_log.json`):**
   For every cut delivered, the editor must record:
   - `episode_id`: Identifier of the source video.
   - `cut_in_ms`: Start timestamp in the source video.
   - `cut_out_ms`: End timestamp in the source video.
   - `hook_rationale`: Why this specific moment was chosen as the opening hook.
   - `payoff_rationale`: What insight or climax resolves the segment.
   - `internal_cuts`: List of `[in_ms, out_ms]` sub-segments if sentences were joined.
   - `editor_id`: Registered identifier of the professional editor.
   - `signed_date`: ISO 8601 date of completion.

---

## 3. Blind Pairwise Evaluation Protocol (200 Clip Pairs)

### 3.1 Blind Staging via `hawedit.comparison_kit`
1. **Randomized Assignment:**
   - For each comparison, `hawedit.comparison_kit.prepare_blind_study` assigns human cut vs HawEdit render to Option A and Option B with cryptographic salt and deterministic seed.
   - Metadata is completely stripped (no HawEdit branding, watermarks, or identifying file metadata).
2. **Viewing Interface:**
   - Raters evaluate pairs independently on mobile devices in portrait 9:16 orientation.
   - Option A and Option B are presented side-by-side or sequentially in random order.

---

## 4. Native Kurdish Rating Form (`ckb`)

The evaluation form is generated via `hawedit.comparison_kit.format_kurdish_form_markdown`:

### فۆرمی هەڵسەنگاندنی کوالێتی کورتە ڤیدیۆکانی هاوێدیت (HawEdit)

تکایە بە وردی سەیری هەردوو ڤیدیۆی (A) و (B) بکە و بەپێی پێوەرەکانی خوارەوە هەڵسەنگاندنیان بۆ بکە.
کامیان وەک کورتە ڤیدیۆیەکی سەربەخۆ، سەرنجڕاکێش، و پرۆفیشناڵ لە تۆڕە کۆمەڵایەتییەکاندا سەرکەوتووترە؟

#### پێوەرەکانی هەڵسەنگاندن
- **ڕاکێشانی سەرنج (Hook):** ئایا ٣ چرکەی یەکەم تا چەند بەهێزە و بینەر دەهێڵێتەوە؟ (پلەی ١ تا ٥)
- **ڕوونی و پەیام (Clarity):** ئایا چیرۆکەکە سەربەخۆیە و پەیامێکی دیار دەگەیەنێت بێ ئەوەی لە کاتی ڕاستەقینە شێوێندرابێت؟ (پلەی ١ تا ٥)
- **شایستەیی بڵاوکردنەوە (Shareability):** ئایا ئەم کورتە ڤیدیۆیە تا چەند شایەنی ئەوەیە بینەر بۆ هاوڕێکانی بنێرێت؟ (پلەی ١ تا ٥)
- **مەترسی چەواشەکاری (Misleading Edit):** ئایا بڕینەکان بوونەتە هۆی گۆڕینی مانای قسەکە یان دروستکردنی مانایەکی چەواشەکار؟ (بەڵێ / نەخێر)
- **هەڵبژاردەی پەسەندکراو (Preferred Option):** کامیان بە گشتی لە ڕووی مۆنتاژ و کاریگەرییەوە پرۆفیشناڵترە؟ (پەڕگەی A / پەڕگەی B / هەردووکیان وەک یەکن)

---

## 5. Acceptance Gate & Statistical Criteria

To declare Phase C complete and satisfy `gemini-agent-prompt-2026-09-13.md`:
1. **Gold Set Manifest:**
   - Stored at `assets/editorial-gold/manifest.json` with file hashes (`sha256`), rater IDs, and submission dates.
2. **Ranker Weight Fitting (Phase C2):**
   - Fit editorial ranker weights on the gold set using ridge regression.
   - Report held-out AUC $\ge 0.80$ on a split the model never saw.
   - Document the fit in `evidence/ranker-fit-*.md`.
3. **H7 Blind Panel (Phase C3):**
   - 20 native raters across 200 pairs.
   - Wilson score 95% confidence interval computed via `hawedit.comparison_kit.analyze_study`.
   - The phrase *"better than an editor"* is strictly prohibited unless `ci_lower > 0.50`. If `ci_lower <= 0.50`, the exact measured win-rate and interval must be published honestly.
