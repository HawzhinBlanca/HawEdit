# Research — Judge Calibration (Task T4.3)

## 1. Problem Statement
BLUEPRINT §3 Stage 4 pins `gemini-2.5-pro` as the Kurdish editorial judge.
Prior audit (D-253, D-257, Task T4.3) identified five specific areas where the editorial evaluation requires rigorous calibration:
1. **Prompt Lacks Concrete Rubric Anchors**:
   The prompt template currently states only: `- hook_score: how strongly the opening seconds hold attention (0..1)`.
   Without calibrated Sorani anchors, model outputs suffer variance and subjective drift across sessions.
2. **Naive Selection Mechanism**:
   When multiple candidates pass editorial gates, selection picks `max(hook_score)`. Hook score alone neglects payoff resolution, narrative meaning fidelity, and Kurdish cultural resonance.
3. **Ungated Metrics**:
   `meaning_fidelity` and `cultural_landing` are recorded in §5's `editorial` block and tracked in `Provenance.thresholds`, but `Clip.assert_renderable()` only checked `hook_score`, `misleading_edit_risk`, and `self_contained`. A clip with poor cultural landing (e.g. 0.20) or compromised fidelity could pass to rendering unchecked.
4. **Repeat-K Agreement**:
   Measuring scoring repeatability and concordance across repeat evaluations ($K=3$) quantifies scoring stability.
5. **Misleading Edit Ceiling Invariant**:
   `MAX_MISLEADING_EDIT_RISK = 0.10` must be strictly maintained as the proven empirical boundary until human editor ground-truth labels (H2) re-derive it.

## 2. Invariants & Calibration Design
- **Rubric Anchors in Prompt**:
  Add calibrated Sorani anchors:
  - `0.20`: دەستپێکی ئاسایی یان سڵاو و دەستپێکی بێ سوود، بێ ڕاکێشانی سەرنج (e.g. conversational filler, standard pleasantries).
  - `0.50`: قسەیەکی ئاسایی یان هەواڵێکی گشتی کە تا ڕادەیەک سەرنجڕاکێشە بەڵام کتوپڕ نییە (e.g. informational statement, moderate curiosity).
  - `0.80+`: پرسیارێکی بوێرانە، بانگەشەیەکی چاوەڕواننەکراو، ململانێ، یان دانپێدانانێکی سەرنجڕاکێش کە دەستبەجێ بینەر رادەگرێت (e.g. bold provocation, shocking confession, high-stakes curiosity).
- **Tournament Ranking**:
  Composite tournament score weighting:
  $$\text{Score} = 0.40 \cdot \text{hook\_score} + 0.30 \cdot \text{payoff\_strength} + 0.20 \cdot \text{meaning\_fidelity} + 0.10 \cdot \text{cultural\_landing}$$
- **Threshold Gating**:
  Add `MIN_MEANING_FIDELITY = 0.70` and `MIN_CULTURAL_LANDING = 0.70` to `Clip.assert_renderable()`.
- **Repeat-K Agreement**:
  Helper `compute_repeat_k_agreement(verdicts)` computing standard deviation and range of scores across repeated runs.

## 3. Real Code Surface Mapping
- `src/hawedit/gemini.py`: `_PROMPT_TEMPLATE`.
- `src/hawedit/clip.py`: `MIN_MEANING_FIDELITY`, `MIN_CULTURAL_LANDING`, `Clip.assert_renderable()`.
- `src/hawedit/judge.py`: `tournament_rank_verdicts`, `compute_repeat_k_agreement`.
- `src/hawedit/pipeline.py`: Candidate selection using `tournament_rank_verdicts`.
