"""`MCG-NJU/VideoChat3-4B` behind Path B — the parser, the clock shift, and the wiring.

Two things are checked here that no other file can check.

**The clock.** VideoChat3 is shown one window and told it starts at zero, so every time it cites
is window-relative. `assert_sv6d_within_window` compares against media-absolute milliseconds.
Those two agree for exactly the windows that start at 0 — and the fixture's first window does,
which is how a missing shift survives an end-to-end run. The tests below use the *second* and
*third* windows and include the case that makes the failure silent rather than loud: a
window-relative time that lands inside the window's absolute range anyway.

**The wiring.** D-053 found five of M5.2's seven guards revertible without the gate noticing,
because the tests covered refusals reachable without weights and nothing covered the path
through the model. So `read_window` is driven here through a stub processor and a stub model
that return the checkpoint's real output text, and the assertions are on the `SceneReading` that
comes out and on the arguments the processor was actually called with.

The strings the parser is fed are not invented. Every one is either verbatim output from
`MCG-NJU/VideoChat3-4B` on the fixture (`evidence/m5-4-path-b.md`) or the exact shape §3
requires be rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hawedit.clip import Sv6d, assert_sv6d_within_window
from hawedit.path_b import PATH_B_MODEL, PathBError, discover_visual
from hawedit.qwen_visual import EmbedderUnavailable
from hawedit.registry import WrongRole
from hawedit.video_input import WindowFrames
from hawedit.video_reader import (
    SV6D_PROMPT,
    VideoChat3Reader,
    build_sv6d,
    parse_sv6d_lines,
)
from hawedit.visual_index import SceneWindow

# Verbatim from the model on `kurdish-speech-3cuts:s1:w0`, the fixture's second scene.
REAL_OUTPUT = """subject | 0.0 | A red number "1" is centered on a white background
aesthetics | 0.0 | The background is plain white, and the number is bright red
camera | 0.0 | The shot is static, with no movement
editing | 0.0 | There are no cuts or transitions
narrative | 0.0 | The number "1" suggests a countdown or a list
retention | 0.0 | The simplicity and boldness of the number may capture attention"""


def a_window(in_ms: int = 1_400, duration_ms: int = 1_400, fps: float = 2.0) -> SceneWindow:
    return SceneWindow(
        media_id="kurdish-speech-3cuts",
        scene_index=1,
        window_index=0,
        in_ms=in_ms,
        out_ms=in_ms + duration_ms,
        fps=fps,
    )


def lines(at: float = 0.0, text: str = "an observation") -> dict[str, tuple[float, str]]:
    return {dimension: (at, text) for dimension in Sv6d.DIMENSIONS}


# --- the parser: §3's "reject output where a claim has no timeline evidence" ---------------


def test_the_models_real_output_parses_to_six_dimensions() -> None:
    parsed = parse_sv6d_lines(REAL_OUTPUT, duration_s=1.4)
    assert sorted(parsed) == sorted(Sv6d.DIMENSIONS)
    assert parsed["subject"] == (0.0, 'A red number "1" is centered on a white background')
    assert parsed["retention"][1].startswith("The simplicity and boldness")


def test_a_missing_dimension_is_refused_by_name() -> None:
    """Filling the gap with a default would put a claim in the reading that no model made."""
    without_camera = "\n".join(
        line for line in REAL_OUTPUT.splitlines() if not line.startswith("camera")
    )
    with pytest.raises(PathBError, match=r"\['camera'\]"):
        parse_sv6d_lines(without_camera, duration_s=1.4)


def test_a_dimension_returned_twice_is_refused() -> None:
    with pytest.raises(PathBError, match="twice"):
        parse_sv6d_lines(REAL_OUTPUT + "\nsubject | 0.5 | a different claim", duration_s=1.4)


def test_a_line_carrying_no_time_field_counts_as_missing() -> None:
    """The earlier prompt wording produced exactly this, and §3 requires it be rejected.

    `subject: … at 0.4s` cites a timestamp in prose, which `Sv6d` alone would accept. It has no
    field this module can shift, so it is not a usable line.
    """
    prose = REAL_OUTPUT.replace(
        'subject | 0.0 | A red number "1" is centered on a white background',
        "subject: a red number is centered at 0.4s",
    )
    with pytest.raises(PathBError, match=r"\['subject'\]"):
        parse_sv6d_lines(prose, duration_s=1.4)


def test_a_time_outside_the_clip_is_refused() -> None:
    """M5.3's `9999s`, caught one layer earlier — before the shift can make it plausible."""
    with pytest.raises(PathBError, match="9999.0 s of a 1.400 s clip"):
        parse_sv6d_lines(REAL_OUTPUT.replace("subject | 0.0", "subject | 9999"), duration_s=1.4)


def test_a_negative_time_cannot_be_expressed_and_a_late_one_is_refused() -> None:
    """The bound is two-sided: 1.5 s of a 1.4 s clip is a moment the model was not shown."""
    with pytest.raises(PathBError, match="1.5 s of a 1.400 s clip"):
        parse_sv6d_lines(REAL_OUTPUT.replace("subject | 0.0", "subject | 1.5"), duration_s=1.4)


def test_a_second_clock_hidden_in_the_description_is_refused() -> None:
    """Only the time in the second field is shifted. A time in the prose would ship unshifted."""
    with pytest.raises(PathBError, match="carries its own timestamps"):
        parse_sv6d_lines(
            REAL_OUTPUT.replace(
                "camera | 0.0 | The shot is static, with no movement",
                "camera | 0.0 | slow push-in starting at 1.2s",
            ),
            duration_s=1.4,
        )


def test_a_description_full_of_digits_is_not_mistaken_for_a_clock() -> None:
    """The positive control for the check above: the real output says `number "1"` and passes."""
    parsed = parse_sv6d_lines(REAL_OUTPUT, duration_s=1.4)
    assert '"1"' in parsed["subject"][1]


# --- the shift, and the reason it cannot be left to the invariant ---------------------------


def test_the_models_zero_becomes_the_windows_own_start() -> None:
    sv6d = build_sv6d(a_window(in_ms=1_400), lines(at=0.0))
    assert sv6d.subject == "1.400s an observation"
    assert_sv6d_within_window(sv6d, 1_400, 2_800)


def test_the_shift_carries_the_offset_and_the_moment_together() -> None:
    sv6d = build_sv6d(a_window(in_ms=2_800, duration_ms=1_362), lines(at=1.2))
    assert sv6d.narrative == "4.000s an observation"


def test_without_the_shift_the_invariant_rejects_the_reading_outright() -> None:
    """The loud half of the failure. This is what M5.4 would do with no shift at all."""
    unshifted = Sv6d(**{dimension: "0.000s an observation" for dimension in Sv6d.DIMENSIONS})
    with pytest.raises(ValueError, match="all outside the scene it describes"):
        assert_sv6d_within_window(unshifted, 1_400, 2_800)


def test_without_the_shift_a_window_relative_time_can_pass_while_being_wrong() -> None:
    """The silent half, and the reason `assert_sv6d_within_window` cannot be the only guard.

    A window running 1000–3000 ms, the model citing 1.5 s into it. Shifted, that is 2500 ms.
    Unshifted the label reads `1.500s`, which lands inside 1000..3000 — so the invariant
    accepts it, and the label is off by the window's start with nothing reporting it.
    """
    window = a_window(in_ms=1_000, duration_ms=2_000)
    shifted = build_sv6d(window, lines(at=1.5))
    assert shifted.subject == "2.500s an observation"

    unshifted = Sv6d(**{dimension: "1.500s an observation" for dimension in Sv6d.DIMENSIONS})
    assert_sv6d_within_window(unshifted, window.in_ms, window.out_ms)  # accepted, and wrong


def test_the_shifted_time_round_trips_through_the_invariants_own_parser() -> None:
    """Milliseconds in, milliseconds out — the label is written in a format `clip.py` reads."""
    from hawedit.clip import parse_timestamps_ms

    sv6d = build_sv6d(a_window(in_ms=1_400), lines(at=0.75))
    assert parse_timestamps_ms(sv6d.subject) == (2_150,)


# --- the prompt -----------------------------------------------------------------------------


def test_the_prompt_asks_for_all_six_dimensions_in_order() -> None:
    rendered = SV6D_PROMPT.format(duration=1.4)
    positions = [rendered.index(dimension) for dimension in Sv6d.DIMENSIONS]
    assert positions == sorted(positions)


def test_the_prompt_states_the_clip_length_it_was_given() -> None:
    """The model is told the range its times must fall in; the parser enforces the same range."""
    assert "1.4 seconds long" in SV6D_PROMPT.format(duration=1.4)
    assert "8.0 seconds long" in SV6D_PROMPT.format(duration=8.0)


# --- construction refuses before 8 GB of weights are read -----------------------------------


def test_a_model_outside_path_bs_role_is_refused(tmp_path: Path) -> None:
    """§7 membership is not a licence to fill any slot — audit finding #8's rule."""
    with pytest.raises(WrongRole):
        VideoChat3Reader(
            tmp_path,
            read_frames=lambda w: WindowFrames(w, (Path("f.jpg"),)),
            score_window=lambda w: 0.5,
            model_id="Qwen3-VL-Embedding-2B",
        )


def test_missing_weights_are_refused_naming_the_fetch_script(tmp_path: Path) -> None:
    with pytest.raises(EmbedderUnavailable, match="fetch-models.sh"):
        VideoChat3Reader(
            tmp_path / "absent",
            read_frames=lambda w: WindowFrames(w, (Path("f.jpg"),)),
            score_window=lambda w: 0.5,
        )


def test_videochat_loader_uses_its_exact_model_type_allowlist(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"model_type":"lightglue"}', encoding="utf-8")
    reader = VideoChat3Reader(
        tmp_path,
        read_frames=lambda w: WindowFrames(w, (Path("f.jpg"),)),
        score_window=lambda w: 0.5,
    )
    with pytest.raises(RuntimeError, match="unapproved"):
        reader._load()


def test_videochat_proves_checkpoint_integrity_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text(
        '{"model_type":"videochat3","text_config":{"model_type":"qwen3"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hawedit.qwen_visual.assert_checkpoint_integrity",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("integrity sentinel")),
    )
    reader = VideoChat3Reader(
        tmp_path,
        read_frames=lambda w: WindowFrames(w, (Path("f.jpg"),)),
        score_window=lambda w: 0.5,
    )
    with pytest.raises(RuntimeError, match="integrity sentinel"):
        reader._load()


def test_videochat_backend_failures_become_path_b_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = VideoChat3Reader(
        tmp_path,
        read_frames=lambda window: WindowFrames(window, (Path("f0.jpg"), Path("f1.jpg"))),
        score_window=lambda _window: 0.5,
    )
    failure = RuntimeError("CUDA out of memory")
    monkeypatch.setattr(reader, "_load", lambda: (_ for _ in ()).throw(failure))

    with pytest.raises(PathBError, match="CUDA out of memory") as caught:
        reader.read_window(a_window())
    assert caught.value.__cause__ is failure


# --- the wiring, driven through a stub processor and model ----------------------------------


class _Ids:
    """Just enough of a tensor for `read_window`: `[0]` for the decode, `.shape[1]` for the cut."""

    def __init__(self, rows: list[list[int]]) -> None:
        self.rows = rows

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.rows), len(self.rows[0]))

    def __getitem__(self, index: int) -> list[int]:
        return self.rows[index]


class _VideoProcessor:
    """VideoChat3's declared preprocessing, which is what the frame-arrival guard reads."""

    fps = 2
    min_frames = 4
    temporal_patch_size = 1


class StubProcessor:
    """Records what it was handed, and returns a prompt with real VideoChat3 timestamps."""

    def __init__(self, answer: str, frames_seen: int = 2) -> None:
        self.prompt = "<0.6 seconds>"
        self.answer = answer
        self.frames_seen = frames_seen
        self.calls: list[dict[str, Any]] = []
        self.tokenizer = self
        self.video_processor = _VideoProcessor()

    def apply_chat_template(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"messages": messages, **kwargs})
        grid = [[self.frames_seen // self.video_processor.temporal_patch_size, 26, 46]]
        return {"input_ids": _Ids([[1, 2, 3]]), "video_grid_thw": grid}

    def decode(self, ids: Any, **kwargs: Any) -> str:
        # The processor decodes the *prompt*; its tokenizer decodes the *answer*. `read_window`
        # calls one of each, and mixing them up is exactly the wiring these tests exist for.
        return self.answer if kwargs.get("skip_special_tokens") else self.prompt


class StubModel:
    def __init__(self) -> None:
        self.generate_kwargs: dict[str, Any] = {}

    def generate(self, **kwargs: Any) -> list[list[int]]:
        self.generate_kwargs = kwargs
        return [[1, 2, 3, 9]]


def a_reader(tmp_path: Path, answer: str = REAL_OUTPUT) -> Any:
    processor, model = StubProcessor(answer), StubModel()
    reader = VideoChat3Reader(
        tmp_path,
        read_frames=lambda w: WindowFrames(w, tuple(Path(f"f{i}.jpg") for i in range(2))),
        score_window=lambda w: 0.4321,
        device="cpu",
    )
    reader._loaded = (processor, model)
    return reader, processor, model


@pytest.fixture(autouse=True)
def _no_pillow_or_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    """These run on a machine with neither Pillow nor torch — `models/` is git-ignored too."""
    monkeypatch.setattr(
        "hawedit.video_reader.load_window_images", lambda frames, processor=None: ["img"] * 2
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", _FakeTorch())


def test_reading_a_window_produces_a_scene_reading_on_the_medias_clock(tmp_path: Path) -> None:
    """The whole path: prompt, guard, generate, parse, shift, score. Asserted on the output."""
    window = a_window(in_ms=1_400)
    reader, _, _ = a_reader(tmp_path)
    reading = reader.read_window(window)

    assert reading.model_id == PATH_B_MODEL
    assert reading.window is window
    assert reading.score == pytest.approx(0.4321)
    # Every label carries the window's own start, not the model's zero.
    assert all(label.startswith("1.400s") for label in reading.sv6d.to_dict().values())


def test_the_reader_passes_video_metadata_at_the_top_level(tmp_path: Path) -> None:
    """D-049 at this call site. Inside the content dict it is accepted and ignored — silently."""
    window = a_window(in_ms=1_400)
    reader, processor, _ = a_reader(tmp_path)
    reader.read_window(window)

    call = processor.calls[0]
    assert call["add_generation_prompt"] is True
    metadata = call["video_metadata"][0]
    assert metadata["fps"] == 2.0
    assert metadata["fps"] * metadata["duration"] == pytest.approx(metadata["total_num_frames"])


def test_a_prompt_the_processor_stamped_wrongly_stops_the_read(tmp_path: Path) -> None:
    """The negative control for the call above: 0.1 s is the 24 fps failure, and it must raise."""
    from hawedit.video_input import TimestampsOutsideWindow

    window = a_window(in_ms=1_400)
    reader, processor, _ = a_reader(tmp_path)
    processor.prompt = "<0.1 seconds>"
    with pytest.raises(TimestampsOutsideWindow):
        reader.read_window(window)


def test_the_reading_is_deterministic_by_construction(tmp_path: Path) -> None:
    """§8.2 counts Recall@K on this order; sampling would make that number noise."""
    window = a_window(in_ms=1_400)
    reader, _, model = a_reader(tmp_path)
    reader.read_window(window)
    assert model.generate_kwargs["do_sample"] is False


def test_read_scenes_drives_the_union_end_to_end(tmp_path: Path) -> None:
    """Through the real `discover_visual`, so all four of its checks pass on real output."""
    windows = tuple(
        SceneWindow(
            media_id="kurdish-speech-3cuts",
            scene_index=i,
            window_index=0,
            in_ms=i * 1_400,
            out_ms=i * 1_400 + 1_400,
            fps=2.0,
        )
        for i in range(3)
    )
    reader, _, _ = a_reader(tmp_path)
    candidates = discover_visual(windows, reader, media_id="kurdish-speech-3cuts")

    assert [c.candidate_id for c in candidates] == [w.window_id for w in windows]
    assert [c.rank for c in candidates] == [1, 2, 3]
    for candidate, window in zip(candidates, windows, strict=True):
        assert candidate.sv6d is not None
        assert candidate.sv6d.subject.startswith(f"{window.in_ms / 1000:.3f}s")


class _FakeTorch:
    """`torch.no_grad` and `torch.bfloat16`, which is all `read_window` touches."""

    bfloat16 = "bfloat16"

    @staticmethod
    def no_grad() -> Any:
        class _Ctx:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *args: Any) -> None:
                return None

        return _Ctx()


def test_a_window_whose_frames_the_processor_resampled_stops_the_read(tmp_path: Path) -> None:
    """The frame-arrival guard, through the adapter rather than only in isolation.

    Six frames handed over, four received — which is exactly what a 1400 ms window at 4 fps did
    on the real checkpoint, and what M5.4's own first evidence run was measuring. D-060.
    """
    from hawedit.video_input import VideoInputError

    window = a_window(in_ms=1_400)
    reader, processor, _ = a_reader(tmp_path)
    processor.frames_seen = 0
    with pytest.raises(VideoInputError, match="dropped 2"):
        reader.read_window(window)
