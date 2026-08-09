"""`MCG-NJU/VideoChat3-4B` behind §3 Stage 3 Path B, and the SV6D prompt.

`path_b.py` defines what a Path B reading is and what the union may do with one; this produces
them from real frames on a real GPU. Nothing here decides discovery policy — the frame budget,
the invented-window and duplicate refusals, and the ordering all live in `path_b.discover_visual`
and are enforced against whatever this returns.

**The model is told a window-relative clock, and there is no way to tell it otherwise.**
VideoChat3's own metadata type computes a frame's time as `video_start_time + index / fps` and
then refuses `video_start_time >= duration` — so on a 1400 ms window the offset it would need
for the fixture's second scene, 1.4 s, is rejected by its own validator. Measured, not assumed.
The model therefore reports times from 0, and turning them into media time is this module's job,
exactly as `video_input`'s docstring says: *"Absolute media time is `window.in_ms + t`, and
adding it is the caller's job."*

**Why that has to happen in code rather than in the prompt.** The alternative is to tell the
model the window starts at 1.4 s and ask it to add the offset itself. A 4B model doing
arithmetic produces a number that is right most of the time, and the failures are silent: an
`Sv6d` label citing 2.9 s on a window running 1.4–2.8 s is a well-formed string that
`assert_sv6d_within_window` rejects, and one citing 2.0 s is a well-formed string it *accepts*
while describing the wrong moment. The shift is arithmetic and belongs where arithmetic is
exact.

**The times come back in a field of their own, not in prose.** `parse_timestamps_ms` cannot tell
a moment from a duration — "slow push-in over 3s, starting 5:04" cites both — so rewriting times
found inside free text would corrupt the durations. The prompt asks for `dimension | seconds |
text` and this module builds the label, putting the media-absolute time in front of the model's
own words. Text that carries a second time of its own is refused rather than shipped, because
that one is window-relative and nothing downstream would say so.

**The score is not the model's.** §3: *"Path B — visual. `VideoChat3-4B` over scenes, **plus
embedding/rerank retrieval**."* The ranking half of Path B is Stage 2's, so `score_window` is
supplied by the caller and this module never invents a number from the reading. Asking a
describer for a relevance score would produce one, in [0, 1], about nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from hawedit.clip import Sv6d, parse_timestamps_ms
from hawedit.path_b import PATH_B_MODEL, PathBError, SceneReading
from hawedit.qwen_visual import (
    DEFAULT_DEVICE,
    EmbedderUnavailable,
    load_processor_and_model,
    release_cuda_model_memory,
)
from hawedit.registry import resolve_role
from hawedit.video_input import (
    VideoInputError,
    WindowFrames,
    load_window_images,
    video_content,
    window_batch,
)
from hawedit.visual_index import SceneWindow

__all__ = [
    "MAX_NEW_TOKENS",
    "SV6D_PROMPT",
    "VideoChat3Reader",
    "build_sv6d",
    "parse_sv6d_lines",
]

_DISCOVERY_ROLE: Final = frozenset({"visual_discovery"})

# Measured on the fixture's three windows: the six lines come back in 100–140 tokens. The
# ceiling is a runaway guard, not a budget — a truncated sixth line is refused by the parser
# rather than silently dropped, so there is no reason to sit close to the real length.
MAX_NEW_TOKENS: Final = 512

# §3 Stage 3: "Use the six-dimension structure from the Leum-VL paper as your output schema …
# subject · aesthetics · camera language · editing · narrative · retention. Every label must
# cite a timestamp. Reject output where a claim has no timeline evidence."
#
# The format is pipe-delimited with the time in a field of its own. Measured across the
# fixture's three windows: 18 of 18 lines came back in this shape, with the time parsed and
# no second time anywhere in the description text. An earlier "name: text, cite a timestamp"
# wording produced a `0.0s:` prefix on some windows and no time at all on others — the same
# model, and output §3 requires be rejected.
SV6D_PROMPT: Final = """This clip is {duration:.1f} seconds long. \
Timestamps in it run from 0.0 to {duration:.1f}.

Describe it on exactly six lines, one per dimension, in this order and this format:

subject | <seconds> | what is on screen and what it does
aesthetics | <seconds> | lighting, colour, framing
camera | <seconds> | shot size and camera movement
editing | <seconds> | cuts, pace, transitions
narrative | <seconds> | the beat that happens
retention | <seconds> | what would keep a viewer watching

<seconds> is the moment in THIS clip your observation is about, a number between 0.0 and \
{duration:.1f}. Write the number alone, no unit. Put no other times in the description text. \
Output the six lines and nothing else."""

_LINE: Final = re.compile(
    r"^\s*(?P<name>[a-z]+)\s*\|\s*(?P<at>[0-9]+(?:\.[0-9]+)?)\s*\|\s*(?P<text>.+?)\s*$"
)


def parse_sv6d_lines(text: str, duration_s: float) -> dict[str, tuple[float, str]]:
    """The model's six lines as `{dimension: (seconds_into_the_window, description)}`.

    Every refusal here is §3's *"Reject output where a claim has no timeline evidence"* applied
    before the claim can become an `Sv6d`, where a well-formed string is indistinguishable from
    an observation.

    Raises:
        PathBError: a dimension is missing, named twice, carries no parseable time, cites a time
            outside the clip it was shown, has no description, or hides a second time inside
            that description.
    """
    found: dict[str, tuple[float, str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _LINE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if name not in Sv6d.DIMENSIONS:
            continue
        if name in found:
            raise PathBError(
                f"the model returned the SV6D dimension {name!r} twice. Two readings of one "
                f"dimension is two claims about the same footage, and nothing chooses between "
                f"them."
            )
        at = float(match.group("at"))
        if not 0.0 <= at <= duration_s:
            raise PathBError(
                f"SV6D {name} cites {at} s of a {duration_s:.3f} s clip. §3 Stage 3: 'Reject "
                f"output where a claim has no timeline evidence' — the model was never shown "
                f"that moment, and once shifted onto the media's clock the number would land "
                f"inside some other scene and read as evidence."
            )
        description = match.group("text")
        cited = parse_timestamps_ms(description)
        if cited:
            raise PathBError(
                f"SV6D {name} description {description!r} carries its own timestamps "
                f"{list(cited)} ms. Those are on the clip's clock, and only the time in the "
                f"second field is shifted onto the media's — shipping both would put two "
                f"different clocks in one label with nothing marking which is which."
            )
        found[name] = (at, description)

    missing = [d for d in Sv6d.DIMENSIONS if d not in found]
    if missing:
        raise PathBError(
            f"the model returned no usable line for {missing}. §3 Stage 3 fixes the schema at "
            f"six dimensions; filling a gap with a default would put a claim in the reading "
            f"that no model made. Raw output was:\n{text[:600]}"
        )
    return found


def build_sv6d(window: SceneWindow, lines: dict[str, tuple[float, str]]) -> Sv6d:
    """The parsed lines as an `Sv6d`, with every time moved onto the media's clock.

    The model is shown one window and told it starts at zero, so `2.5` means 2.5 s into *this
    scene*. `Sv6d` and `assert_sv6d_within_window` are checked against media-absolute
    milliseconds, which is also what §5's clip documents and §3 Stage 5's fusion use. Handing
    the model's own number through unchanged is correct for exactly the windows that start at 0
    and wrong for every other one — and wrong quietly, since a window-relative time frequently
    lands inside some window's absolute range.
    """
    labels: dict[str, str] = {}
    for dimension, (at, description) in lines.items():
        absolute_ms = window.in_ms + round(at * 1000)
        labels[dimension] = f"{absolute_ms / 1000:.3f}s {description}"
    return Sv6d(**labels)


class VideoChat3Reader:
    """`MCG-NJU/VideoChat3-4B` behind `path_b.VideoUnderstanding`.

    Loading is deferred to first use, so constructing one costs nothing and cannot fail on a
    machine without the weights — the same arrangement as `QwenVisualEmbedder`, and for the same
    reason: `pipeline.py` may build one before it knows whether Path B will run.

    Args:
        model_dir: where the checkpoint lives.
        read_frames: the frames for a window. Passed in rather than extracted here so that the
            frames a window was *embedded* from in Stage 2 are the frames it is *read* from
            here; two independent extractions of "the same" window differ at the tail.
        score_window: §3's "plus embedding/rerank retrieval" half. See the module docstring.
    """

    def __init__(
        self,
        model_dir: Path,
        read_frames: Callable[[SceneWindow], WindowFrames],
        score_window: Callable[[SceneWindow], float],
        device: str = DEFAULT_DEVICE,
        model_id: str = PATH_B_MODEL,
    ) -> None:
        # §7 first: a model outside the registry, or one in it for a different job, never gets
        # as far as loading 8 GB of weights.
        resolve_role(model_id, _DISCOVERY_ROLE, "the Path B video reader")
        if not model_dir.is_dir():
            raise EmbedderUnavailable(
                f"no weights at {model_dir}. Run `hawedit-fetch-models {model_id}` — "
                f"§7's registry drives it, so it cannot fetch the wrong model."
            )
        self.model_dir = model_dir
        self.read_frames = read_frames
        self.score_window = score_window
        self.device = device
        self.model_id = model_id
        self._loaded: tuple[Any, Any] | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._loaded is None:
            self._loaded = load_processor_and_model(
                self.model_dir,
                self.device,
                model_id=self.model_id,
                allowed_model_types=frozenset({"videochat3", "qwen3"}),
                trust_remote_code=True,
                causal_lm=True,
                configure=_use_sdpa_vision,
            )
        return self._loaded

    def close(self) -> None:
        """Drop VideoChat3 weights after the survivor-reading phase; reload on next use."""
        was_loaded = self._loaded is not None
        self._loaded = None
        if was_loaded:
            release_cuda_model_memory(self.device)

    def read_window(self, window: SceneWindow) -> SceneReading:
        try:
            return self._read_window(window)
        except (EmbedderUnavailable, PathBError, VideoInputError):
            raise
        except (OSError, RuntimeError) as exc:
            raise PathBError(
                f"{self.model_id} failed while reading {window.window_id}: {exc}"
            ) from exc

    def _read_window(self, window: SceneWindow) -> SceneReading:
        """One scene, read and turned into §3's SV6D schema on the media's clock."""
        import torch

        processor, model = self._load()
        frames = self.read_frames(window)
        duration_s = window.duration_ms / 1000.0
        messages = [
            {
                "role": "user",
                "content": [
                    video_content(load_window_images(frames, processor)),
                    {"type": "text", "text": SV6D_PROMPT.format(duration=duration_s)},
                ],
            }
        ]
        # The reading is generated, so the prompt has to end where the answer begins.
        batch = window_batch(processor, messages, frames, add_generation_prompt=True)
        placed = {k: (v.to(self.device) if hasattr(v, "to") else v) for k, v in dict(batch).items()}
        for key in ("pixel_values", "pixel_values_videos"):
            if hasattr(placed.get(key), "to"):
                placed[key] = placed[key].to(torch.bfloat16)
        with torch.no_grad():
            # `do_sample=False` for the same reason `rerank` breaks ties deterministically:
            # §8.2 counts Recall@K on this ordering, and a reading that varies between runs
            # makes that number noise rather than a measurement.
            generated = model.generate(**placed, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        answer = processor.tokenizer.decode(
            generated[0][batch["input_ids"].shape[1] :], skip_special_tokens=True
        )
        return SceneReading(
            window=window,
            sv6d=build_sv6d(window, parse_sv6d_lines(answer, duration_s)),
            score=self.score_window(window),
            model_id=self.model_id,
        )

    def read_scenes(self, windows: Sequence[SceneWindow]) -> tuple[SceneReading, ...]:
        """§3 Stage 3 Path B over these scenes, one reading each.

        One call per window rather than one model batch: §3 calls segmentation mandatory and
        gives VRAM figures per frame count. `discover_visual` additionally packs its input into
        at-most-256-frame calls for any other implementation of this protocol.
        """
        return tuple(self.read_window(window) for window in windows)


def _use_sdpa_vision(config: Any) -> None:
    """VideoChat3's vision tower defaults to an attention kernel that is `None` here.

    `VL_VISION_ATTENTION_FUNCTIONS` in the checkpoint's own modelling code holds
    `flash_attention_2`, `sdpa` and `eager`, selected by `vision_config.attn_impl`. The default
    is the first, `flash_attn_varlen_func` resolves to `None` without flash-attn, and flash-attn
    publishes no Windows wheels. `sdpa` is torch's own and needs nothing. D-055.
    """
    config.vision_config.attn_impl = "sdpa"
