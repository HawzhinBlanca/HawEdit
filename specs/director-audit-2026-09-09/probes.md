# Reproducing the decisive audit findings

Run from the project root with its canonical Python environment. These are bounded diagnostic calls, not replacement gate tests. They do not create or modify a source video, application code or approval record.

## Missing-video all-clear

```python
from pathlib import Path
from hawedit.render_critic import RenderedSequenceContext, inspect_rendered_sequence

missing = Path('specs/director-audit-2026-09-09/DOES_NOT_EXIST.mp4')
assert not missing.exists()
result = inspect_rendered_sequence(
    RenderedSequenceContext(render_path=missing, duration_ms=10000),
    claim_all_clear=True,
)
print(result.is_all_clear, result.coverage_ratio, len(result.defects))
result.assert_verdict_grounded()
```

Observed: `True 1.0 0`, and the assertion method returns without an exception. No source path, decoded frame, audio sample or real render was supplied.

## Under-maximum inputs bypass condensation; early windows consume the quota

```python
from hawedit.condenser import condense_story, condense_multiple_arcs
from hawedit.sentences import Sentence
from hawedit.transcripts import Word
from hawedit.sanity_gate import check_narrative_integrity

def sentence(i, text, duration=10000):
    return Sentence(
        (Word(w=text, start_ms=i*duration, end_ms=(i+1)*duration, conf=.99),),
        True,
    )

plan = condense_story(
    [sentence(i, 'ئەمە') for i in range(4)],
    target_duration_ms=20000,
    max_duration_ms=60000,
)
print(plan.condensed_duration_ms, plan.pruned_sentence_indices)
print(check_narrative_integrity(plan))

plans = condense_multiple_arcs(
    [sentence(i, f'item{i}') for i in range(100)], max_clips=3
)
print(len(plans), max(end for p in plans for start, end in p.retained_spans))
```

Observed: 40,000 ms retained, no pruned sentences, narrative check `(True, ())`; the 1,000,000 ms synthetic source returns three plans with latest retained end 240,000 ms. These are control-flow probes, not an editorial-quality benchmark. The target duration is an ideal, so the first observation specifically establishes skipped pruning rather than a strict target constraint failure.

## Dashboard flow

Launch `python -m hawedit.web 8080`, open its localhost page, select no file and click Generate. It reaches Ready. Inspect `/api/jobs` and `/api/status`: the generated job names `source.mp4`; both clips refer to `/media/ep29-pro-threat-reel.mp4`; status includes `audit_passed: true`. The audit used real browser interactions, not inserted application state. Responses were saved as `dashboard-probe.json`.

## Exact current output frames

Inspect `work/ep29-highlights-master/ep29-highlights-reel.mp4`, verified SHA-256 in `media-inspection.json`. Decode the actual frame at 34 seconds and 44 seconds using FFmpeg. Saved fresh samples are `captures/highlights-34s.jpg` and `captures/highlights-44s.jpg`. Both show table/window without the speaker. This demonstrates specific output defects, not their full duration.

The full contact sheets selected exact frame numbers at 25 fps for times 2, 12, 22, 24, 34, 40, 44 seconds, then scaled each to 216×384 and tiled seven columns. No padding frames were added. Sampling cannot certify motion, sound, correct source attribution or continuous face presence.
