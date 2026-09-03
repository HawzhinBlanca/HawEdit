# Research: Visual-Variety-Aware Selection (Task T4.6)

## 1. Problem & Context
As identified in `HANDOFF.md` §5 and `specs/pro-edit/impact-map.md`:
> *"selection ranks on hook score alone, so it is quietly biased toward visually flat footage: judged spans average one source cut per 19.8 s vs the episode's 11.1 s, and the first shipped clip had zero."*

Currently, when multiple candidate moments pass §2 editorial thresholds, the winner is selected in `src/hawedit/pipeline.py:2078-2085`:
```python
winner, winning_run, verdict = max(
    shippable,
    key=lambda item: (
        item[2].hook_score,
        getattr(item[2], "payoff_strength", 0.0),
        getattr(item[2], "ends_on_a_beat", False),
    ),
)
```
Because the judge assigns discrete scores from rubrics, ties are frequent. When two candidates tie on `hook_score`, `payoff_strength`, and `ends_on_a_beat`, the first evaluated candidate wins regardless of visual dynamics. A candidate that takes place entirely on a single flat camera angle is favored over a candidate with dynamic multi-camera cuts.

## 2. Requirement & Constraints (Task T4.6)
From `specs/pro-grade-program/tasks.md` Task T4.6:
> **Task T4.6 (P2): Visual-variety-aware selection, behind a flag.**
> Tiebreak passers by source cuts per second within the span; default **off**.
> Measure on ep29 which clip each policy picks.
> Hawa's editorial call: keep default **off** so ranking is never altered unilaterally.

## 3. Mathematical & Algorithmic Formulation
Stage 0 (`IngestResult.shot_cuts_ms`) already detects and records all source camera cut timestamps in milliseconds from the media itself.
For any candidate span $[T_{in}, T_{out}]$:
- Duration in seconds: $D_s = \frac{T_{out} - T_{in}}{1000}$
- Source cuts within span: $N_{cuts} = \sum_{c \in \text{shot\_cuts\_ms}} \mathbb{I}(T_{in} < c < T_{out})$
- Visual variety metric (cuts per second):
  $$V = \begin{cases} \frac{N_{cuts}}{D_s} & \text{if } D_s > 0 \\ 0.0 & \text{otherwise} \end{cases}$$

Candidate sorting key:
When `visual_variety=False` (default):
$$K = (\text{hook\_score}, \text{payoff\_strength}, \text{ends\_on\_a\_beat})$$
When `visual_variety=True`:
$$K_{variety} = (\text{hook\_score}, \text{payoff\_strength}, \text{ends\_on\_a\_beat}, V)$$

## 4. Architectural Grounding
- Function `calculate_visual_variety(span: tuple[int, int], shot_cuts_ms: Sequence[int]) -> float` in `src/hawedit/pipeline.py`.
- Integration into `_shippable_sort_key` in `run_pipeline`.
- CLI flag `--visual-variety` in `build_parser` (default `False`).
- Opt-in parameter `visual_variety: bool = False` in `run_pipeline`.
