# Research: Boundary Extension That Completes a Sentence (Task T4.8)

## 1. Context & Motivation
In `BLUEPRINT.md` §3 Stage 5 (`fuse_boundary`), anchor boundaries are aligned with physical shot cuts, speaker turn transitions, and natural silence.
When a boundary expands outward (e.g. into an adjacent shot cut or VAD pause), it can overlap with words that were not part of the initially selected sentence range (`selected`).
Currently, `pipeline.py` (lines 2224-2246) checks:
```python
selected_words = {word for sentence in selected for word in sentence.words}
uncaptioned = [
    word for sentence in sentences for word in sentence.words
    if word not in selected_words
    and word.start_ms < boundary.final_out_ms
    and word.end_ms > boundary.final_in_ms
]
if uncaptioned:
    # Skip boundary with StageSkipped("uncaptioned speech")
```
In real podcast footage (such as ep29), almost any shot cut or soft expansion slightly overlaps speech regions. If adjacent unselected words belong to a complete sentence that entirely fits within the extended boundary, skipping the whole clip is overly punitive.

## 2. Invariant Requirements
Task T4.8 specifies:
"When a shot-cut or turn extension pulls in unselected words, allow it if and only if those words complete a sentence; refuse otherwise (as now)."

To preserve all Kurdish editorial invariants:
1. **No partial sentences**: If an extension touches only *part* of a sentence (i.e. some of its words lie outside `boundary.final_in_ms..boundary.final_out_ms`), it must NOT be absorbed and MUST be refused as `StageSkipped("uncaptioned speech")`.
2. **No uncaptioned speech**: If touched sentences are completely contained within the boundary, they are appended to `selected`. All their words are included in `clip.transcript` and `captions.ass`.
3. **Contiguity**: Sentences absorbed must be strictly adjacent to the current `selected` range, preserving coherent temporal continuity.
