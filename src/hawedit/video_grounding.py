"""`MCG-NJU/TimeLens2-4B` behind §3 Stage 5's evidence contract.

`timelens.py` defines what a visual-evidence interval is and which ones Stage 5 may use; this
produces them from real frames on a real GPU. No policy lives here — the relevance gate, the
overlap rule and §3's "not a cut" warning are all in `timelens.py` and `boundary.py` and are
enforced against whatever this returns.

**The query is the caller's, and so is the claim.** TimeLens2 is a temporal-grounding model: it
takes a query and returns spans, and it returns *only* spans — no description, no confidence. So
`VisualEvidenceInterval.claim` records what was asked rather than what the model said, and
`confidence` stays `None`. Reporting 0.0 there would be a measurement the model never made.

**The clock.** The model answers in seconds from the start of the window it was shown.
`VisualEvidenceInterval.from_window` moves that onto the media's clock, and it lives beside the
type rather than here so a second producer cannot omit it — see D-062 for what an unshifted
interval does to a boundary.

**One thing this module cannot supply, and says so.** §3 Stage 5 treats the interval as one input
among five, and the query it is grounded against has to come from somewhere — the anchored
sentence, the judge's verdict, a Path A candidate. Choosing that is Stage 5's composition, not
this adapter's, so `ground` takes the query as an argument and refuses an empty one rather than
inventing a default.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from hawedit.qwen_visual import DEFAULT_DEVICE, EmbedderUnavailable, load_processor_and_model
from hawedit.registry import resolve_role
from hawedit.timelens import TIMELENS_MODEL, VisualEvidenceInterval
from hawedit.video_input import (
    WindowFrames,
    load_window_images,
    video_content,
    window_batch,
)
from hawedit.visual_index import SceneWindow

__all__ = [
    "GROUNDING_PROMPT",
    "MAX_NEW_TOKENS",
    "GroundingError",
    "TimeLens2Grounder",
    "parse_spans",
]

_EVIDENCE_ROLE: Final = frozenset({"temporal_evidence"})

# Verbatim from the checkpoint's own model card. Not paraphrased: the model was tuned to answer
# this question in this wording and to emit that exact container. A reworded prompt is a different
# question to the same weights, and the reply would still parse.
GROUNDING_PROMPT: Final = (
    'Given the query: "{query}", return ALL time spans (in seconds) where the query is '
    "relevant.\n"
    "Output format MUST be a JSON array of [start, end] pairs.\n"
)

# Measured on the fixture: the whole answer is `[[1.0, 2.0]]` — under twenty tokens. The card
# suggests 4096; this is a runaway guard, and a truncated array fails `parse_spans` rather than
# being silently read as a shorter list.
MAX_NEW_TOKENS: Final = 256


class GroundingError(RuntimeError):
    """The grounding model returned something Stage 5 cannot use as evidence."""


def parse_spans(answer: str) -> tuple[tuple[float, float], ...]:
    """The `[[start, end], …]` array the card specifies, as pairs of seconds.

    Window-relative — `VisualEvidenceInterval.from_window` puts them on the media's clock.

    Raises:
        GroundingError: no array, malformed pairs, or a non-numeric bound. An empty array is
            **not** an error: "this model has nothing to say about this query here" is a real
            answer, and `interval_end_for_fusion` already treats absence as no adjustment rather
            than as an out-point of zero.
    """
    start_at = answer.find("[")
    if start_at < 0:
        raise GroundingError(
            f"no JSON array in the model's answer. §3 Stage 5 takes an interval or nothing; "
            f"prose would have to be interpreted, and an interval read out of a sentence by "
            f"guesswork moves a real boundary. Answer was: {answer[:300]!r}"
        )
    # `raw_decode` from the first bracket rather than a regex for `[[…]]`. The first draft here
    # used that regex and the real model refused it on its first run: asked about the blue "2"
    # while shown the black "0", TimeLens2 answered `[]` — the correct answer — and an array of
    # arrays cannot match an empty one. A found-nothing reply is the commonest reply there is.
    try:
        raw, _ = json.JSONDecoder().raw_decode(answer[start_at:])
    except json.JSONDecodeError as exc:
        raise GroundingError(
            f"the model's array is not valid JSON: {exc}. Answer was: {answer[:300]!r}"
        ) from exc
    if not isinstance(raw, list):
        raise GroundingError(f"expected a JSON array of pairs, got {type(raw).__name__}")

    spans: list[tuple[float, float]] = []
    for pair in raw:
        if not isinstance(pair, list) or len(pair) != 2:
            raise GroundingError(
                f"expected [start, end] pairs and got {pair!r}. A three-element entry or a bare "
                f"number is a different contract, and reading the first two values out of it "
                f"would be a guess about which."
            )
        start, end = pair
        if any(
            isinstance(bound, bool)
            or not isinstance(bound, int | float)
            or (isinstance(bound, float) and not math.isfinite(bound))
            for bound in pair
        ):
            raise GroundingError(f"span bounds must be finite JSON numbers, got {pair!r}")
        try:
            spans.append((float(start), float(end)))
        except OverflowError as exc:
            raise GroundingError(f"span bounds must fit finite JSON numbers, got {pair!r}") from exc
    return tuple(spans)


class TimeLens2Grounder:
    """`MCG-NJU/TimeLens2-4B` producing `timelens.VisualEvidenceInterval`s.

    Loading is deferred to first use, so constructing one costs nothing and cannot fail on a
    machine without the weights — the same arrangement as the Stage 2 and Path B adapters.

    Args:
        model_dir: where the checkpoint lives.
        read_frames: the frames for a window, passed in rather than extracted here so that the
            frames a window was embedded from in Stage 2 are the frames it is grounded from.
    """

    def __init__(
        self,
        model_dir: Path,
        read_frames: Any,
        device: str = DEFAULT_DEVICE,
        model_id: str = TIMELENS_MODEL,
    ) -> None:
        # §7 first: a model outside the registry, or one in it for a different job, never gets as
        # far as loading 9 GB of weights.
        resolve_role(model_id, _EVIDENCE_ROLE, "the visual temporal evidence model")
        if not model_dir.is_dir():
            raise EmbedderUnavailable(
                f"no weights at {model_dir}. Run `bash scripts/fetch-models.sh {model_id}` — "
                f"§7's registry drives it, so it cannot fetch the wrong model."
            )
        self.model_dir = model_dir
        self.read_frames = read_frames
        self.device = device
        self.model_id = model_id
        self._loaded: tuple[Any, Any] | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._loaded is None:
            # No keyword arguments: TimeLens2 is a plain `Qwen3VLForConditionalGeneration` with
            # `tie_word_embeddings: true` at both config levels, so it needs none of VideoChat3's
            # three workarounds and reports `missing_keys: NONE` on the pinned transformers.
            self._loaded = load_processor_and_model(
                self.model_dir, self.device, model_id=self.model_id
            )
        return self._loaded

    def ground(self, window: SceneWindow, query: str) -> tuple[VisualEvidenceInterval, ...]:
        """Where in `window` the model says `query`'s visual evidence is, on the media's clock.

        Returns an empty tuple when the model found nothing, which `interval_end_for_fusion`
        already distinguishes from an out-point of zero.

        Raises:
            GroundingError: the query is empty, or the answer is not the array the card specifies.
            ValueError: a returned span falls outside the window the model was shown.
        """
        import torch

        if not query.strip():
            raise GroundingError(
                "grounding needs a query. §3 Stage 5 asks where the evidence for *this idea* is; "
                "an empty query would ground against nothing and still return a span."
            )
        processor, model = self._load()
        frames: WindowFrames = self.read_frames(window)
        messages = [
            {
                "role": "user",
                "content": [
                    video_content(load_window_images(frames, processor)),
                    {"type": "text", "text": GROUNDING_PROMPT.format(query=query)},
                ],
            }
        ]
        batch = window_batch(processor, messages, frames, add_generation_prompt=True)
        placed = {k: (v.to(self.device) if hasattr(v, "to") else v) for k, v in dict(batch).items()}
        with torch.no_grad():
            # Greedy, for the reason `rerank` breaks ties deterministically: §8.2 counts on this
            # output, and a boundary that moves between runs is not a measurement. The card's
            # `temperature=0.01, top_k=1` is greedy by a longer route.
            generated = model.generate(**placed, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        answer = processor.tokenizer.decode(
            generated[0][batch["input_ids"].shape[1] :], skip_special_tokens=True
        )
        claim = f"evidence for: {query}"
        return tuple(
            VisualEvidenceInterval.from_window(window, start, end, claim, model_id=self.model_id)
            for start, end in parse_spans(answer)
        )

    def ground_all(
        self, windows: Sequence[SceneWindow], query: str
    ) -> tuple[VisualEvidenceInterval, ...]:
        """Every window's evidence for one query, flattened for `interval_end_for_fusion`.

        One call per window rather than one batched call, for the same reason Path B does:
        §3 gives VRAM figures per frame count, and a window is the unit the frame budget and the
        64-frame ceiling are both expressed in.
        """
        return tuple(interval for window in windows for interval in self.ground(window, query))
