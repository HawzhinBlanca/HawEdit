# Adversarial pass 20 — scene-window paths and TimeLens status

Date: 2026-08-10
Baseline: `a713dfd23e6265ef146d2ec3d2c712dbbbac05e0`

## Finding

`SceneWindow.media_id` was accepted without the repository's portable identifier validation.
Three production consumers derive extraction directories from `window.window_id` by translating
only `:` to `_`:

- `VisualFrameCache` in `visual_pipeline.py`;
- `QwenVisualEmbedder.embed_window` in `qwen_visual.py`;
- the TimeLens frame loader composed by `pipeline.py`.

The public type therefore made a path claim its consumers could not safely uphold. This exact
control reproduced the escape before the fix:

```text
window_id= ../../outside:s0:w0
target= C:\safe\run\frames\..\..\outside_s0_w0
escapes= True
```

The standard CLI happened to validate its media id first. That does not protect direct library
use, injected adapters, a future construction site, or a deserialiser that correctly trusts the
type's own invariants.

## Fix and discriminating controls

`SceneWindow.__post_init__` now calls the shared `validate_media_id` before any frame arithmetic.
The test matrix refuses:

- `../../outside` and `..\outside`;
- a colon that would be confused with the logical ID separators;
- a hidden filename;
- Windows device name `CON`;
- a trailing period.

A portable Kurdish identifier (`هەوا episode-12`) remains accepted. Testing Windows hazards on
every host distinguishes a cross-platform contract from a POSIX-only separator check.

Focused verification from the checkout source:

```text
155 passed
Ruff: all checks passed
Ruff format: 2 files already formatted
mypy: success, no issues in 1 source file
```

## TimeLens ledger correction

The historical M6.3 row still said TimeLens was not wired into `run_pipeline`, but the later
composition amendment and current code contradict it. The runner selects overlapping scene
windows, uses the canonical selected transcript slice as the query, calls `ground_all`, fuses
relevant media-time intervals, and closes the grounder. M6.3 remains PARTIAL because accuracy on
the labelled real-footage corpus is not accepted (`BLOCKED.md` #1), not because composition is
missing.
