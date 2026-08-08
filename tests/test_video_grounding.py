"""`MCG-NJU/TimeLens2-4B` behind §3 Stage 5 — the parser, the clock, and the wiring.

Every answer string fed to the parser here is verbatim from the real model on the fixture
(`evidence/m6-3-grounding.md`), including `[]` — which is what it returns when asked about a scene
that does not contain the query, and which the first draft of `parse_spans` rejected as malformed.

The wiring is driven through a stub processor and model rather than 9 GB of weights, for D-053's
reason: the audit that found five revertible guards found them because the tests covered refusals
reachable without weights and nothing covered the path through the model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from hawedit.qwen_visual import EmbedderUnavailable
from hawedit.registry import WrongRole
from hawedit.timelens import TIMELENS_MODEL
from hawedit.video_grounding import (
    GROUNDING_PROMPT,
    MAX_NEW_TOKENS,
    GroundingError,
    TimeLens2Grounder,
    parse_spans,
)
from hawedit.video_input import VideoInputError, WindowFrames
from hawedit.visual_index import SceneWindow


def a_window(in_ms: int = 2_800, out_ms: int = 4_162, fps: float = 3.0) -> SceneWindow:
    return SceneWindow(
        media_id="kurdish-speech-3cuts",
        scene_index=2,
        window_index=0,
        in_ms=in_ms,
        out_ms=out_ms,
        fps=fps,
    )


# --- the parser, on real answers -----------------------------------------------------------


def test_the_models_real_answer_parses() -> None:
    assert parse_spans("[[0.0, 0.8]]") == ((0.0, 0.8),)
    assert parse_spans("[[1.0, 2.0]]") == ((1.0, 2.0),)


def test_found_nothing_is_an_answer_and_not_an_error() -> None:
    """`[]` is what the model returns for a scene the query is not in — measured, on scenes 0
    and 1 of the fixture. The first draft matched `[[…]]` with a regex and refused it, which
    would have made the commonest correct reply a crash on the first real episode."""
    assert parse_spans("[]") == ()


def test_several_spans_all_come_through() -> None:
    """The prompt asks for ALL relevant spans; dropping any would silently narrow the evidence."""
    assert parse_spans("[[0.0, 0.8], [1.2, 1.35]]") == ((0.0, 0.8), (1.2, 1.35))


def test_prose_with_no_array_is_refused() -> None:
    with pytest.raises(GroundingError, match="no JSON array"):
        parse_spans("The relevant moment is around two seconds in.")


def test_a_one_element_pair_is_refused_rather_than_padded() -> None:
    with pytest.raises(GroundingError, match=r"expected \[start, end\] pairs"):
        parse_spans("[[1.0]]")


def test_a_three_element_entry_is_refused_rather_than_truncated() -> None:
    """Reading the first two of three would be a guess about which two."""
    with pytest.raises(GroundingError, match=r"expected \[start, end\] pairs"):
        parse_spans("[[1.0, 2.0, 0.9]]")


def test_non_numeric_bounds_are_refused() -> None:
    with pytest.raises(GroundingError, match="must be numbers"):
        parse_spans('[["start", "end"]]')


def test_a_truncated_array_is_refused_rather_than_read_short() -> None:
    """Generation hitting the token ceiling mid-array must not look like a shorter answer."""
    with pytest.raises(GroundingError, match="not valid JSON"):
        parse_spans("[[0.0, 0.8], [1.2,")


def test_trailing_prose_after_the_array_is_tolerated() -> None:
    """`raw_decode` stops at the end of the value, so a chatty suffix is not a failure."""
    assert parse_spans("[[0.0, 0.8]] — that is where it appears.") == ((0.0, 0.8),)


# --- the prompt ----------------------------------------------------------------------------


def test_the_prompt_is_the_checkpoints_own_wording() -> None:
    """Quoted from the model card, not paraphrased: a reworded question to the same weights is a
    different question, and the reply would still parse."""
    rendered = GROUNDING_PROMPT.format(query="a speaker gestures")
    assert 'Given the query: "a speaker gestures"' in rendered
    assert "JSON array of [start, end] pairs" in rendered


# --- construction refuses before 9 GB of weights are read -----------------------------------


def test_a_model_outside_stage_5s_role_is_refused(tmp_path: Path) -> None:
    with pytest.raises(WrongRole):
        TimeLens2Grounder(tmp_path, read_frames=lambda w: None, model_id="Qwen3-VL-Embedding-2B")


def test_missing_weights_are_refused_naming_the_fetch_script(tmp_path: Path) -> None:
    with pytest.raises(EmbedderUnavailable, match="fetch-models.sh"):
        TimeLens2Grounder(tmp_path / "absent", read_frames=lambda w: None)


# --- the wiring -----------------------------------------------------------------------------


class _Ids:
    def __init__(self, rows: list[list[int]]) -> None:
        self.rows = rows

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.rows), len(self.rows[0]))

    def __getitem__(self, index: int) -> list[int]:
        return self.rows[index]


class _VideoProcessor:
    fps = 2
    min_frames = 4
    temporal_patch_size = 2
    do_resize = False
    patch_size = 16
    merge_size = 2
    size: ClassVar[dict[str, int]] = {"shortest_edge": 4096, "longest_edge": 25165824}


class StubProcessor:
    def __init__(self, answer: str, frames_seen: int = 4) -> None:
        self.answer = answer
        self.prompt = "<0.2 seconds><1.0 seconds>"
        self.frames_seen = frames_seen
        self.calls: list[dict[str, Any]] = []
        self.tokenizer = self
        self.video_processor = _VideoProcessor()

    def apply_chat_template(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"messages": messages, **kwargs})
        grid = [[self.frames_seen // self.video_processor.temporal_patch_size, 22, 40]]
        return {"input_ids": _Ids([[1, 2, 3]]), "video_grid_thw": grid}

    def decode(self, ids: Any, **kwargs: Any) -> str:
        return self.answer if kwargs.get("skip_special_tokens") else self.prompt


class StubModel:
    def __init__(self) -> None:
        self.generate_kwargs: dict[str, Any] = {}

    def generate(self, **kwargs: Any) -> list[list[int]]:
        self.generate_kwargs = kwargs
        return [[1, 2, 3, 9]]


class _FakeTorch:
    bfloat16 = "bfloat16"

    @staticmethod
    def no_grad() -> Any:
        class _Ctx:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *args: Any) -> None:
                return None

        return _Ctx()


def a_grounder(tmp_path: Path, answer: str = "[[0.0, 0.8]]") -> Any:
    processor, model = StubProcessor(answer), StubModel()
    grounder = TimeLens2Grounder(
        tmp_path,
        read_frames=lambda w: WindowFrames(w, tuple(Path(f"f{i}.jpg") for i in range(4))),
        device="cpu",
    )
    grounder._loaded = (processor, model)
    return grounder, processor, model


@pytest.fixture(autouse=True)
def _no_pillow_or_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hawedit.video_grounding.load_window_images", lambda frames, processor=None: ["img"] * 4
    )
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())


def test_grounding_returns_intervals_on_the_medias_clock(tmp_path: Path) -> None:
    """The whole path, asserted on the interval that comes out — not on the request."""
    grounder, _, _ = a_grounder(tmp_path)
    intervals = grounder.ground(a_window(), "a red number 2 on a blue background")
    assert len(intervals) == 1
    assert intervals[0].span == (2_800, 3_600)
    assert intervals[0].model_id == TIMELENS_MODEL
    assert intervals[0].claim == "evidence for: a red number 2 on a blue background"


def test_a_found_nothing_answer_yields_no_intervals(tmp_path: Path) -> None:
    grounder, _, _ = a_grounder(tmp_path, answer="[]")
    assert grounder.ground(a_window(), "a speaker gestures") == ()


def test_an_empty_query_is_refused_rather_than_grounded_against_nothing(tmp_path: Path) -> None:
    grounder, _, _ = a_grounder(tmp_path)
    with pytest.raises(GroundingError, match="needs a query"):
        grounder.ground(a_window(), "   ")


def test_the_grounder_passes_video_metadata_at_the_top_level(tmp_path: Path) -> None:
    """D-049 at this call site — the third adapter to need it."""
    grounder, processor, _ = a_grounder(tmp_path)
    grounder.ground(a_window(), "a speaker gestures")
    call = processor.calls[0]
    assert call["add_generation_prompt"] is True
    metadata = call["video_metadata"][0]
    assert metadata["fps"] == 3.0
    assert metadata["fps"] * metadata["duration"] == pytest.approx(metadata["total_num_frames"])


def test_frames_the_processor_resampled_stop_the_grounding(tmp_path: Path) -> None:
    """D-060 at this call site: a span grounded in frames the model never saw is not evidence."""
    grounder, processor, _ = a_grounder(tmp_path)
    processor.frames_seen = 2
    with pytest.raises(VideoInputError, match="dropped 2"):
        grounder.ground(a_window(), "a speaker gestures")


def test_the_grounding_is_deterministic_by_construction(tmp_path: Path) -> None:
    """A boundary that moves between runs is not a measurement."""
    grounder, _, model = a_grounder(tmp_path)
    grounder.ground(a_window(), "a speaker gestures")
    assert model.generate_kwargs["do_sample"] is False
    assert model.generate_kwargs["max_new_tokens"] == MAX_NEW_TOKENS


def test_ground_all_flattens_every_windows_evidence(tmp_path: Path) -> None:
    grounder, _, _ = a_grounder(tmp_path)
    windows = tuple(
        SceneWindow(
            media_id="kurdish-speech-3cuts",
            scene_index=i,
            window_index=0,
            in_ms=i * 1_400,
            out_ms=i * 1_400 + 1_362,
            fps=3.0,
        )
        for i in range(3)
    )
    intervals = grounder.ground_all(windows, "a speaker gestures")
    assert [i.span for i in intervals] == [(0, 800), (1_400, 2_200), (2_800, 3_600)]
