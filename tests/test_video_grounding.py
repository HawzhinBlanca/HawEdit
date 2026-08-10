"""`MCG-NJU/TimeLens2-4B` behind §3 Stage 5 — the parser, the clock, and the wiring.

Every answer string fed to the parser here is verbatim from the real model on the fixture
(`evidence/m6-3-grounding.md`), including `[]` — which is what it returns when asked about a scene
that does not contain the query, and which the first draft of `parse_spans` rejected as malformed.

The wiring is driven through a stub processor and model rather than 9 GB of weights, for D-053's
reason: the audit that found five revertible guards found them because the tests covered refusals
reachable without weights and nothing covered the path through the model.
"""

from __future__ import annotations

import os
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


def a_window(in_ms: int = 2_800, out_ms: int = 4_162, fps: float = 2.0) -> SceneWindow:
    return SceneWindow(
        media_id="kurdish-speech-3cuts",
        scene_index=2,
        window_index=0,
        in_ms=in_ms,
        out_ms=out_ms,
        fps=fps,
    )


def test_grounder_close_is_idempotent_and_next_use_reloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released: list[str] = []
    loaded = (object(), object())

    def unused_frames(_window: SceneWindow) -> WindowFrames:
        raise AssertionError("close must not read frames")

    grounder = TimeLens2Grounder(tmp_path, unused_frames, device="cuda:1")
    grounder._loaded = (object(), object())
    monkeypatch.setattr("hawedit.video_grounding.release_cuda_model_memory", released.append)
    monkeypatch.setattr(
        "hawedit.video_grounding.load_processor_and_model", lambda *_args, **_kwargs: loaded
    )

    grounder.close()
    grounder.close()
    assert released == ["cuda:1"]
    assert grounder._loaded is None
    assert grounder._load() is loaded


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
    with pytest.raises(GroundingError, match="must be finite JSON numbers"):
        parse_spans('[["start", "end"]]')


@pytest.mark.parametrize(
    "answer",
    ("[[false, true]]", "[[NaN, 1.0]]", "[[0.0, Infinity]]", f"[[0, {10**1_000}]]"),
)
def test_boolean_and_non_finite_bounds_are_refused(answer: str) -> None:
    with pytest.raises(GroundingError, match="finite JSON numbers"):
        parse_spans(answer)


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


def test_missing_weights_are_lazy_at_construction_and_refused_at_runtime(tmp_path: Path) -> None:
    absent = tmp_path / "absent"
    grounder = TimeLens2Grounder(absent, read_frames=lambda w: None)

    assert grounder.model_dir == absent
    with pytest.raises(EmbedderUnavailable, match="hawedit-fetch-models"):
        grounder.ground(a_window(), "a speaker gestures")


def test_timelens_proves_checkpoint_integrity_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text(
        '{"model_type":"qwen3_vl","text_config":{"model_type":"qwen3_vl_text"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hawedit.qwen_visual.verified_checkpoint_access",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("integrity sentinel")),
    )
    grounder = TimeLens2Grounder(tmp_path, read_frames=lambda w: None)
    with pytest.raises(RuntimeError, match="integrity sentinel"):
        grounder._load()


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


def test_grounding_deletes_extracted_source_pixels_after_model_use(tmp_path: Path) -> None:
    private = tmp_path / "private-frames"
    private.mkdir()
    paths = tuple(private / f"f{index}.jpg" for index in range(4))
    for path in paths:
        path.write_bytes(b"source pixel")
    identity = os.lstat(private)
    frames = WindowFrames(
        a_window(),
        paths,
        _owner_dir=private,
        _owner_identity=(identity.st_dev, identity.st_ino),
    )
    grounder, _, _ = a_grounder(tmp_path)
    grounder.read_frames = lambda _window: frames

    intervals = grounder.ground(a_window(), "a speaker gestures")

    assert intervals
    assert not private.exists()


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
    assert metadata["fps"] == 2.0
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


@pytest.mark.parametrize(
    "failure",
    [
        ImportError("torch is unavailable"),
        OSError("checkpoint read failed"),
        RuntimeError("CUDA allocation failed"),
    ],
    ids=["import-error", "os-error", "runtime-error"],
)
def test_model_operational_failures_are_normalized_at_the_grounder_boundary(
    tmp_path: Path, failure: Exception
) -> None:
    grounder, _, model = a_grounder(tmp_path)

    def fail_generate(**kwargs: Any) -> list[list[int]]:
        raise failure

    model.generate = fail_generate
    with pytest.raises(GroundingError, match=rf"{type(failure).__name__}: {failure}") as caught:
        grounder.ground(a_window(), "a speaker gestures")

    assert caught.value.__cause__ is failure


def test_cleanup_privacy_note_survives_grounder_error_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "private-frames"
    private.mkdir()
    paths = tuple(private / f"f{index}.jpg" for index in range(4))
    for path in paths:
        path.write_bytes(b"source pixel")
    identity = os.lstat(private)
    frames = WindowFrames(
        a_window(),
        paths,
        _owner_dir=private,
        _owner_identity=(identity.st_dev, identity.st_ino),
    )
    grounder, _, model = a_grounder(tmp_path)
    grounder.read_frames = lambda _window: frames
    primary = RuntimeError("CUDA allocation failed")
    model.generate = lambda **_kwargs: (_ for _ in ()).throw(primary)
    real_unlink = Path.unlink

    def refuse_private_frame(path: Path, missing_ok: bool = False) -> None:
        if path.parent == private:
            raise PermissionError("scanner holds the pixel")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refuse_private_frame)
    with pytest.raises(GroundingError, match="CUDA allocation failed") as caught:
        grounder.ground(a_window(), "a speaker gestures")

    assert caught.value.__cause__ is primary
    assert any("private visual frame cleanup failed" in note for note in caught.value.__notes__)
    monkeypatch.setattr(Path, "unlink", real_unlink)
    frames.cleanup()


def test_programmer_exception_from_grounding_model_is_not_normalized(tmp_path: Path) -> None:
    grounder, _, model = a_grounder(tmp_path)

    def fail_generate(**kwargs: Any) -> list[list[int]]:
        raise AssertionError("model adapter invariant broke")

    model.generate = fail_generate
    with pytest.raises(AssertionError, match="model adapter invariant broke"):
        grounder.ground(a_window(), "a speaker gestures")


def test_out_of_window_model_span_remains_a_schema_value_error(tmp_path: Path) -> None:
    grounder, _, _ = a_grounder(tmp_path, answer="[[0.0, 9.0]]")
    with pytest.raises(ValueError, match="span outside the window"):
        grounder.ground(a_window(), "a speaker gestures")


def test_ground_all_flattens_every_windows_evidence(tmp_path: Path) -> None:
    grounder, _, _ = a_grounder(tmp_path)
    windows = tuple(
        SceneWindow(
            media_id="kurdish-speech-3cuts",
            scene_index=i,
            window_index=0,
            in_ms=i * 1_400,
            out_ms=i * 1_400 + 1_362,
            fps=2.0,
        )
        for i in range(3)
    )
    intervals = grounder.ground_all(windows, "a speaker gestures")
    assert [i.span for i in intervals] == [(0, 800), (1_400, 2_200), (2_800, 3_600)]
