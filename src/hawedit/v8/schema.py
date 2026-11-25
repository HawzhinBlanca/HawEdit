"""HawEdit V8 declarative DirectorScript schema & Hard Camera Restraint compiler (D-382)."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, TypeVar, cast

from hawedit.transcripts import Word

__all__ = [
    "CAMERA_CUT_SNAP_WINDOW_MS",
    "CAMERA_MAX_MOVING_FRACTION",
    "CAMERA_MAX_SCALE",
    "CAMERA_MIN_SCALE",
    "CAMERA_MOTION_EPS",
    "CAMERA_MOVE_STEP_MS",
    "CAPTION_MAX_SHORT_3_CHARS",
    "CAPTION_MAX_WORDS",
    "SLOW_PUSH_EASE_OUT_MS",
    "STUDIO_GRADE_FILTER",
    "CameraMove",
    "CameraMoveKind",
    "CaptionBeat",
    "CritiqueVerdict",
    "CutKind",
    "CutRegion",
    "DirectorScript",
    "DirectorScriptError",
    "VisualInterrupt",
    "VisualInterruptPosition",
    "WordRepair",
    "compile_restrained_camera_filter",
    "max_camera_moves_for_duration",
    "snap_camera_moves_to_cuts",
    "validate_director_script",
]

CutKind = Literal["filler", "silence", "tangent", "cold_open"]
CameraMoveKind = Literal["locked", "punch_cut", "slow_push", "wide_release"]
VisualInterruptPosition = Literal["top", "chest"]

_CUT_KINDS: Final[frozenset[str]] = frozenset({"filler", "silence", "tangent", "cold_open"})
_CAMERA_MOVE_KINDS: Final[frozenset[str]] = frozenset(
    {"locked", "punch_cut", "slow_push", "wide_release"}
)
_VISUAL_INTERRUPT_POSITIONS: Final[frozenset[str]] = frozenset({"top", "chest"})
_HEX_COLOR_RE: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
_T = TypeVar("_T")

CAMERA_MIN_SCALE: Final[float] = 1.00
CAMERA_MAX_SCALE: Final[float] = 1.16
CAMERA_MAX_MOVING_FRACTION: Final[float] = 0.25
CAMERA_MOTION_EPS: Final[float] = 1e-3
CAMERA_MOVE_STEP_MS: Final[int] = 15_000
CAMERA_CUT_SNAP_WINDOW_MS: Final[int] = 700
SLOW_PUSH_EASE_OUT_MS: Final[int] = 450
CAPTION_MAX_WORDS: Final[int] = 3
CAPTION_MAX_SHORT_3_CHARS: Final[int] = 14
_JUMP_CUT_DELTA_THRESHOLD: Final[float] = 0.04
_MIN_SNAPPED_PUNCH_MS: Final[int] = 250
_CUT_ALIGN_TOLERANCE_MS: Final[int] = 50

STUDIO_GRADE_FILTER: Final[str] = (
    "eq=contrast=1.04:saturation=1.08:brightness=0.01,"
    "unsharp=3:3:0.30:3:3:0.0,vignette=PI/8:eval=init"
)


class DirectorScriptError(ValueError):
    """Raised when a V8 DirectorScript or CritiqueVerdict violates schema or edit laws."""


def _obj(
    value: Any, ctx: str, req: frozenset[str], opt: frozenset[str] = frozenset()
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DirectorScriptError(f"{ctx} must be a JSON object, got {type(value).__name__}")
    keys = set(value.keys())
    if missing := req - keys:
        raise DirectorScriptError(f"{ctx} missing required field(s): {sorted(missing)}")
    if unknown := keys - (req | opt):
        raise DirectorScriptError(f"{ctx} contains unknown field(s): {sorted(unknown)}")
    return value


def _req_int(value: Any, ctx: str, *, min_value: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DirectorScriptError(f"{ctx} must be an integer, got {value!r}")
    if min_value is not None and value < min_value:
        raise DirectorScriptError(f"{ctx} must be >= {min_value}, got {value}")
    return int(value)


def _req_float(value: Any, ctx: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DirectorScriptError(f"{ctx} must be a finite number, got {value!r}")
    out = float(value)
    if not math.isfinite(out):
        raise DirectorScriptError(f"{ctx} must be finite, got {value!r}")
    return out


def _req_str(value: Any, ctx: str, *, allow_empty: bool = False, single_line: bool = False) -> str:
    if not isinstance(value, str):
        raise DirectorScriptError(f"{ctx} must be a string, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise DirectorScriptError(f"{ctx} must be a non-empty string")
    if "\x00" in value:
        raise DirectorScriptError(f"{ctx} must not contain NUL bytes")
    if single_line and value and value.splitlines() != [value]:
        raise DirectorScriptError(f"{ctx} must be a single line, got {value!r}")
    return value


def _req_span(start_ms: Any, end_ms: Any, ctx: str) -> tuple[int, int]:
    s = _req_int(start_ms, f"{ctx}.start_ms", min_value=0)
    e = _req_int(end_ms, f"{ctx}.end_ms", min_value=1)
    if e <= s:
        raise DirectorScriptError(f"{ctx}.end_ms ({e}) must be > start_ms ({s})")
    return s, e


def _req_list(value: Any, ctx: str) -> Sequence[Any]:
    if not isinstance(value, list | tuple):
        raise DirectorScriptError(f"{ctx} must be a list, got {type(value).__name__}")
    return value


def _req_tuple_of(value: Any, item_type: type[_T], ctx: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise DirectorScriptError(f"{ctx} must be a tuple[{item_type.__name__}, ...]")


def _parse_json_str(raw: str, ctx: str) -> Any:
    if not isinstance(raw, str):
        raise DirectorScriptError(f"{ctx} JSON must be a string")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DirectorScriptError(f"Invalid {ctx} JSON: {exc}") from exc


def max_camera_moves_for_duration(duration_ms: int) -> int:
    """Return the maximum permitted active camera moves for ``duration_ms`` (D-382)."""
    _req_int(duration_ms, "duration_ms", min_value=1)
    return max(2, math.ceil(duration_ms / CAMERA_MOVE_STEP_MS))


@dataclass(frozen=True, slots=True)
class WordRepair:
    """Audio-grounded spelling or loanword repair for one aligned transcript word."""

    word_index: int
    original: str
    repaired: str
    reason: str

    def __post_init__(self) -> None:
        _req_int(self.word_index, "WordRepair.word_index", min_value=0)
        _req_str(self.original, "WordRepair.original", single_line=True)
        _req_str(self.repaired, "WordRepair.repaired", single_line=True)
        _req_str(self.reason, "WordRepair.reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_index": self.word_index,
            "original": self.original,
            "repaired": self.repaired,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WordRepair:
        o = _obj(data, "WordRepair", frozenset({"word_index", "original", "repaired", "reason"}))
        return cls(
            word_index=o["word_index"],
            original=o["original"],
            repaired=o["repaired"],
            reason=o["reason"],
        )


@dataclass(frozen=True, slots=True)
class CutRegion:
    """One semantic editorial cut window in clip-relative milliseconds."""

    start_ms: int
    end_ms: int
    kind: CutKind
    reason: str

    def __post_init__(self) -> None:
        _req_span(self.start_ms, self.end_ms, "CutRegion")
        if self.kind not in _CUT_KINDS:
            raise DirectorScriptError(f"CutRegion.kind invalid: {self.kind!r}")
        _req_str(self.reason, "CutRegion.reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "kind": self.kind,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CutRegion:
        o = _obj(data, "CutRegion", frozenset({"start_ms", "end_ms", "kind", "reason"}))
        return cls(start_ms=o["start_ms"], end_ms=o["end_ms"], kind=o["kind"], reason=o["reason"])


@dataclass(frozen=True, slots=True)
class CameraMove:
    """One Director-earned camera framing window (default outside moves is 1.00× locked)."""

    start_ms: int
    end_ms: int
    kind: CameraMoveKind
    scale_start: float
    scale_end: float
    reason: str

    def __post_init__(self) -> None:
        _req_span(self.start_ms, self.end_ms, "CameraMove")
        if self.kind not in _CAMERA_MOVE_KINDS:
            raise DirectorScriptError(f"CameraMove.kind invalid: {self.kind!r}")
        _req_float(self.scale_start, "CameraMove.scale_start")
        _req_float(self.scale_end, "CameraMove.scale_end")
        _req_str(self.reason, "CameraMove.reason")

    @property
    def is_moving(self) -> bool:
        """True when zoom changes across the window (counts toward <= 25% motion budget)."""
        return abs(float(self.scale_end) - float(self.scale_start)) > CAMERA_MOTION_EPS

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "kind": self.kind,
            "scale_start": float(self.scale_start),
            "scale_end": float(self.scale_end),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CameraMove:
        o = _obj(
            data,
            "CameraMove",
            frozenset({"start_ms", "end_ms", "kind", "scale_start", "scale_end", "reason"}),
        )
        return cls(
            start_ms=o["start_ms"],
            end_ms=o["end_ms"],
            kind=o["kind"],
            scale_start=_req_float(o["scale_start"], "CameraMove.scale_start"),
            scale_end=_req_float(o["scale_end"], "CameraMove.scale_end"),
            reason=o["reason"],
        )


@dataclass(frozen=True, slots=True)
class CaptionBeat:
    """One viral 1–2 word (max 3 short) subtitle chunk with optional semantic power word."""

    word_indices: tuple[int, ...]
    power_word_index: int | None = None
    accent_color: str = "#FFE500"

    def __post_init__(self) -> None:
        if not isinstance(self.word_indices, tuple) or not self.word_indices:
            raise DirectorScriptError("CaptionBeat.word_indices must be a non-empty tuple of ints")
        prev = -1
        for idx in self.word_indices:
            val = _req_int(idx, "CaptionBeat.word_indices[]", min_value=0)
            if val <= prev:
                raise DirectorScriptError(
                    f"CaptionBeat.word_indices must be strictly increasing, got {self.word_indices}"
                )
            prev = val
        if self.power_word_index is not None:
            pw = _req_int(self.power_word_index, "CaptionBeat.power_word_index", min_value=0)
            if pw not in self.word_indices:
                raise DirectorScriptError(
                    f"CaptionBeat.power_word_index ({pw}) must belong to word_indices "
                    f"{self.word_indices}"
                )
        color = _req_str(self.accent_color, "CaptionBeat.accent_color", single_line=True)
        if _HEX_COLOR_RE.fullmatch(color) is None:
            raise DirectorScriptError(
                f"CaptionBeat.accent_color must be a #RRGGBB hex color, got {color!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_indices": list(self.word_indices),
            "power_word_index": self.power_word_index,
            "accent_color": self.accent_color,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CaptionBeat:
        o = _obj(
            data,
            "CaptionBeat",
            frozenset({"word_indices"}),
            frozenset({"power_word_index", "accent_color"}),
        )
        indices = tuple(_req_list(o["word_indices"], "CaptionBeat.word_indices"))
        accent = "#FFE500" if o.get("accent_color") is None else o["accent_color"]
        return cls(
            word_indices=cast(tuple[int, ...], indices),
            power_word_index=o.get("power_word_index"),
            accent_color=accent,
        )


@dataclass(frozen=True, slots=True)
class VisualInterrupt:
    """Earned Kurdish on-screen callout card placed at top or chest."""

    start_ms: int
    end_ms: int
    text_ckb: str
    position: VisualInterruptPosition = "top"

    def __post_init__(self) -> None:
        _req_span(self.start_ms, self.end_ms, "VisualInterrupt")
        _req_str(self.text_ckb, "VisualInterrupt.text_ckb", single_line=True)
        if self.position not in _VISUAL_INTERRUPT_POSITIONS:
            raise DirectorScriptError(f"VisualInterrupt.position invalid: {self.position!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text_ckb": self.text_ckb,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VisualInterrupt:
        o = _obj(
            data,
            "VisualInterrupt",
            frozenset({"start_ms", "end_ms", "text_ckb"}),
            frozenset({"position"}),
        )
        pos = "top" if o.get("position") is None else o["position"]
        return cls(
            start_ms=o["start_ms"],
            end_ms=o["end_ms"],
            text_ckb=o["text_ckb"],
            position=cast(VisualInterruptPosition, pos),
        )


@dataclass(frozen=True, slots=True)
class CritiqueVerdict:
    """Watch-Before-Ship multimodal critic decision with optional surgical JSON patch."""

    approved: bool
    score: float
    issues: tuple[str, ...] = ()
    patch: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool):
            raise DirectorScriptError(
                f"CritiqueVerdict.approved must be a boolean, got {self.approved!r}"
            )
        score = _req_float(self.score, "CritiqueVerdict.score")
        if not (0.0 <= score <= 100.0):
            raise DirectorScriptError(f"CritiqueVerdict.score must be in [0.0, 100.0], got {score}")
        if not isinstance(self.issues, tuple):
            raise DirectorScriptError("CritiqueVerdict.issues must be a tuple of strings")
        for issue in self.issues:
            _req_str(issue, "CritiqueVerdict.issues[]")
        if self.patch is not None and not isinstance(self.patch, dict):
            raise DirectorScriptError("CritiqueVerdict.patch must be a dict or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "score": float(self.score),
            "issues": list(self.issues),
            "patch": dict(self.patch) if self.patch is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CritiqueVerdict:
        o = _obj(
            data,
            "CritiqueVerdict",
            frozenset({"approved", "score"}),
            frozenset({"issues", "patch"}),
        )
        issues = tuple(_req_list(o.get("issues", ()), "CritiqueVerdict.issues"))
        raw_patch = o.get("patch")
        if raw_patch is not None and not isinstance(raw_patch, Mapping):
            raise DirectorScriptError("CritiqueVerdict.patch must be a JSON object or null")
        return cls(
            approved=o["approved"],
            score=_req_float(o["score"], "CritiqueVerdict.score"),
            issues=cast(tuple[str, ...], issues),
            patch=dict(raw_patch) if raw_patch is not None else None,
        )

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, raw: str) -> CritiqueVerdict:
        return cls.from_dict(_parse_json_str(raw, "CritiqueVerdict"))


@dataclass(frozen=True, slots=True)
class DirectorScript:
    """Declarative creative edit script emitted by the V8 Multimodal Director."""

    clip_id: str
    hook_title_ckb: str
    word_repairs: tuple[WordRepair, ...] = ()
    cuts: tuple[CutRegion, ...] = ()
    camera_moves: tuple[CameraMove, ...] = ()
    caption_beats: tuple[CaptionBeat, ...] = ()
    visual_interrupts: tuple[VisualInterrupt, ...] = ()
    cold_open_span_ms: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        _req_str(self.clip_id, "DirectorScript.clip_id", single_line=True)
        _req_str(
            self.hook_title_ckb, "DirectorScript.hook_title_ckb", allow_empty=True, single_line=True
        )
        _req_tuple_of(self.word_repairs, WordRepair, "DirectorScript.word_repairs")
        _req_tuple_of(self.cuts, CutRegion, "DirectorScript.cuts")
        _req_tuple_of(self.camera_moves, CameraMove, "DirectorScript.camera_moves")
        _req_tuple_of(self.caption_beats, CaptionBeat, "DirectorScript.caption_beats")
        _req_tuple_of(self.visual_interrupts, VisualInterrupt, "DirectorScript.visual_interrupts")
        if self.cold_open_span_ms is not None:
            if not isinstance(self.cold_open_span_ms, tuple) or len(self.cold_open_span_ms) != 2:
                raise DirectorScriptError(
                    "DirectorScript.cold_open_span_ms must be a (start_ms, end_ms) tuple or None"
                )
            _req_span(
                self.cold_open_span_ms[0],
                self.cold_open_span_ms[1],
                "DirectorScript.cold_open_span_ms",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "hook_title_ckb": self.hook_title_ckb,
            "word_repairs": [x.to_dict() for x in self.word_repairs],
            "cuts": [x.to_dict() for x in self.cuts],
            "camera_moves": [x.to_dict() for x in self.camera_moves],
            "caption_beats": [x.to_dict() for x in self.caption_beats],
            "visual_interrupts": [x.to_dict() for x in self.visual_interrupts],
            "cold_open_span_ms": (
                list(self.cold_open_span_ms) if self.cold_open_span_ms is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DirectorScript:
        o = _obj(
            data,
            "DirectorScript",
            frozenset({"clip_id", "hook_title_ckb"}),
            frozenset(
                {
                    "word_repairs",
                    "cuts",
                    "camera_moves",
                    "caption_beats",
                    "visual_interrupts",
                    "cold_open_span_ms",
                }
            ),
        )
        raw_co = o.get("cold_open_span_ms")
        cold_open: tuple[int, int] | None = None
        if raw_co is not None:
            seq = _req_list(raw_co, "DirectorScript.cold_open_span_ms")
            if len(seq) != 2:
                raise DirectorScriptError("DirectorScript.cold_open_span_ms must have 2 integers")
            cold_open = _req_span(seq[0], seq[1], "DirectorScript.cold_open_span_ms")
        return cls(
            clip_id=o["clip_id"],
            hook_title_ckb=o["hook_title_ckb"],
            word_repairs=tuple(
                WordRepair.from_dict(x)
                for x in _req_list(o.get("word_repairs", ()), "DirectorScript.word_repairs")
            ),
            cuts=tuple(
                CutRegion.from_dict(x) for x in _req_list(o.get("cuts", ()), "DirectorScript.cuts")
            ),
            camera_moves=tuple(
                CameraMove.from_dict(x)
                for x in _req_list(o.get("camera_moves", ()), "DirectorScript.camera_moves")
            ),
            caption_beats=tuple(
                CaptionBeat.from_dict(x)
                for x in _req_list(o.get("caption_beats", ()), "DirectorScript.caption_beats")
            ),
            visual_interrupts=tuple(
                VisualInterrupt.from_dict(x)
                for x in _req_list(
                    o.get("visual_interrupts", ()), "DirectorScript.visual_interrupts"
                )
            ),
            cold_open_span_ms=cold_open,
        )

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, raw: str) -> DirectorScript:
        return cls.from_dict(_parse_json_str(raw, "DirectorScript"))


def _validate_camera_moves(
    camera_moves: Sequence[CameraMove],
    *,
    duration_ms: int,
) -> tuple[CameraMove, ...]:
    """Enforce Hard Camera Restraint Law (D-382) and return moves sorted by start_ms."""
    _req_int(duration_ms, "duration_ms", min_value=1)
    sorted_moves = tuple(sorted(camera_moves, key=lambda m: (m.start_ms, m.end_ms)))

    for idx, move in enumerate(sorted_moves):
        if move.end_ms > duration_ms:
            raise DirectorScriptError(
                f"CameraMove[{idx}] end_ms ({move.end_ms}) exceeds duration_ms ({duration_ms})"
            )
        if not (CAMERA_MIN_SCALE <= move.scale_start <= CAMERA_MAX_SCALE):
            raise DirectorScriptError(
                f"CameraMove[{idx}].scale_start ({move.scale_start:.4f}) outside "
                f"[{CAMERA_MIN_SCALE:.2f}, {CAMERA_MAX_SCALE:.2f}] (D-382)"
            )
        if not (CAMERA_MIN_SCALE <= move.scale_end <= CAMERA_MAX_SCALE):
            raise DirectorScriptError(
                f"CameraMove[{idx}].scale_end ({move.scale_end:.4f}) outside "
                f"[{CAMERA_MIN_SCALE:.2f}, {CAMERA_MAX_SCALE:.2f}] (D-382)"
            )
        if move.kind == "locked" and move.is_moving:
            raise DirectorScriptError(
                f"CameraMove[{idx}] kind='locked' cannot change scale "
                f"({move.scale_start:.4f} -> {move.scale_end:.4f})"
            )
        if idx > 0 and move.start_ms < sorted_moves[idx - 1].end_ms:
            raise DirectorScriptError(
                f"Overlapping CameraMove windows: [{sorted_moves[idx - 1].start_ms}, "
                f"{sorted_moves[idx - 1].end_ms}) and [{move.start_ms}, {move.end_ms})"
            )

    active_count = sum(1 for m in sorted_moves if m.kind != "locked")
    max_moves = max_camera_moves_for_duration(duration_ms)
    if active_count > max_moves:
        raise DirectorScriptError(
            f"Too many active camera moves: {active_count} > max {max_moves} "
            f"for {duration_ms} ms clip (D-382)"
        )

    moving_ms = sum(m.end_ms - m.start_ms for m in sorted_moves if m.is_moving)
    if moving_ms * 4 > duration_ms:
        pct = 100.0 * moving_ms / duration_ms
        raise DirectorScriptError(
            f"Moving-camera screen time {moving_ms} ms ({pct:.1f}%) exceeds 25.0% restraint "
            f"budget for {duration_ms} ms clip (D-382: >= 75% locked tripod required)"
        )
    return sorted_moves


def _assert_not_mid_word(boundary_ms: int, words: Sequence[Word], *, label: str) -> None:
    for idx, word in enumerate(words):
        if word.start_ms < boundary_ms < word.end_ms:
            raise DirectorScriptError(
                f"{label} boundary {boundary_ms} ms slices word[{idx}] {word.w!r} "
                f"[{word.start_ms}, {word.end_ms}] (E3 zero mid-word cut rule)"
            )


def validate_director_script(
    script: DirectorScript,
    *,
    duration_ms: int,
    words: Sequence[Word],
) -> None:
    """Strictly validate a ``DirectorScript`` against D-382, D-383, and E3 invariants."""
    _req_int(duration_ms, "duration_ms", min_value=1)

    word_texts = [word.w for word in words]
    seen_repairs: set[int] = set()
    for r in script.word_repairs:
        if r.word_index >= len(words):
            raise DirectorScriptError(
                f"WordRepair.word_index ({r.word_index}) out of bounds for {len(words)} words"
            )
        if r.word_index in seen_repairs:
            raise DirectorScriptError(f"Duplicate WordRepair for word_index {r.word_index}")
        seen_repairs.add(r.word_index)
        if words[r.word_index].w != r.original:
            raise DirectorScriptError(
                f"WordRepair[{r.word_index}].original ({r.original!r}) "
                f"does not match transcript word ({words[r.word_index].w!r})"
            )
        word_texts[r.word_index] = r.repaired

    removal_cuts: list[CutRegion] = []
    for cut in sorted(script.cuts, key=lambda c: (c.start_ms, c.end_ms)):
        if cut.end_ms > duration_ms:
            raise DirectorScriptError(
                f"CutRegion [{cut.start_ms}, {cut.end_ms}] exceeds duration_ms ({duration_ms})"
            )
        _assert_not_mid_word(cut.start_ms, words, label=f"CutRegion({cut.kind}).start_ms")
        _assert_not_mid_word(cut.end_ms, words, label=f"CutRegion({cut.kind}).end_ms")
        if cut.kind != "cold_open":
            if removal_cuts and cut.start_ms < removal_cuts[-1].end_ms:
                raise DirectorScriptError(
                    f"Overlapping CutRegion windows: [{removal_cuts[-1].start_ms}, "
                    f"{removal_cuts[-1].end_ms}) and [{cut.start_ms}, {cut.end_ms})"
                )
            removal_cuts.append(cut)

    removed_ms = sum(c.end_ms - c.start_ms for c in removal_cuts)
    min_keep = min(1_000, duration_ms)
    if duration_ms - removed_ms < min_keep:
        raise DirectorScriptError(
            f"CutRegion removals ({removed_ms} ms) leave < {min_keep} ms of {duration_ms} ms clip"
        )

    if script.cold_open_span_ms is not None:
        co_s, co_e = script.cold_open_span_ms
        if co_e > duration_ms:
            raise DirectorScriptError(
                f"cold_open_span_ms [{co_s}, {co_e}] exceeds duration_ms ({duration_ms})"
            )
        _assert_not_mid_word(co_s, words, label="cold_open_span_ms.start_ms")
        _assert_not_mid_word(co_e, words, label="cold_open_span_ms.end_ms")

    _validate_camera_moves(script.camera_moves, duration_ms=duration_ms)

    seen_cap: set[int] = set()
    for b_idx, beat in enumerate(script.caption_beats):
        if len(beat.word_indices) > CAPTION_MAX_WORDS:
            raise DirectorScriptError(
                f"CaptionBeat[{b_idx}] has {len(beat.word_indices)} words; "
                f"maximum is {CAPTION_MAX_WORDS} (D-383: never 4+ words)"
            )
        for w_idx in beat.word_indices:
            if w_idx >= len(words):
                raise DirectorScriptError(
                    f"CaptionBeat[{b_idx}] word_index ({w_idx}) out of bounds ({len(words)} words)"
                )
            if w_idx in seen_cap:
                raise DirectorScriptError(f"CaptionBeat[{b_idx}] duplicates word_index {w_idx}")
            seen_cap.add(w_idx)
        if len(beat.word_indices) == CAPTION_MAX_WORDS:
            joined = " ".join(word_texts[i] for i in beat.word_indices)
            if len(joined) > CAPTION_MAX_SHORT_3_CHARS:
                raise DirectorScriptError(
                    f"CaptionBeat[{b_idx}] 3-word chunk {joined!r} is {len(joined)} chars "
                    f"(exceeds <= {CAPTION_MAX_SHORT_3_CHARS} char limit, D-383)"
                )

    sorted_vi = sorted(script.visual_interrupts, key=lambda v: (v.start_ms, v.end_ms))
    for idx, vi in enumerate(sorted_vi):
        if vi.end_ms > duration_ms:
            raise DirectorScriptError(
                f"VisualInterrupt[{idx}] end_ms ({vi.end_ms}) exceeds duration_ms ({duration_ms})"
            )
        if idx > 0 and vi.start_ms < sorted_vi[idx - 1].end_ms:
            raise DirectorScriptError(
                f"Overlapping VisualInterrupt windows: [{sorted_vi[idx - 1].start_ms}, "
                f"{sorted_vi[idx - 1].end_ms}) and [{vi.start_ms}, {vi.end_ms})"
            )


def _nearest_cut_within(t_ms: int, cuts: Sequence[int], window_ms: int) -> int | None:
    best: int | None = None
    best_dist = window_ms + 1
    for c in cuts:
        dist = abs(c - t_ms)
        if dist <= window_ms and dist < best_dist:
            best = c
            best_dist = dist
    return best


def snap_camera_moves_to_cuts(
    moves: Sequence[CameraMove],
    shot_cuts_ms: Sequence[int],
    jump_cuts_ms: Sequence[int],
    duration_ms: int,
    *,
    snap_window_ms: int = CAMERA_CUT_SNAP_WINDOW_MS,
) -> tuple[CameraMove, ...]:
    """Align ``CameraMove`` boundaries onto nearby real shot/jump cuts (D-387).

    - ``punch_cut`` / ``wide_release``: snap ``start_ms`` and ``end_ms`` onto any real cut
      within ``<= snap_window_ms`` (default 700 ms) so a digital punch never double-fires
      half a second before a real camera cut, and normalize ``scale_start = scale_end`` so
      it cuts instantaneously with zero ramp.
    - ``slow_push``: snap ``end_ms`` onto any cut within ``<= snap_window_ms`` for an
      invisible cut-aligned release (shifting ``start_ms`` forward if needed to keep the
      ``<= 25%`` moving-camera budget intact).
    """
    _req_int(duration_ms, "duration_ms", min_value=1)
    _req_int(snap_window_ms, "snap_window_ms", min_value=0)
    sorted_moves = _validate_camera_moves(moves, duration_ms=duration_ms)
    if not sorted_moves:
        return ()

    cuts = sorted({int(c) for c in (*shot_cuts_ms, *jump_cuts_ms) if 0 < int(c) < duration_ms})
    snapped: list[CameraMove] = []
    prev_end = 0

    for move in sorted_moves:
        if move.kind in ("punch_cut", "wide_release"):
            new_start = move.start_ms
            new_end = move.end_ms
            if (snap_s := _nearest_cut_within(new_start, cuts, snap_window_ms)) is not None:
                new_start = snap_s
            if (snap_e := _nearest_cut_within(new_end, cuts, snap_window_ms)) is not None:
                new_end = snap_e
            new_start = max(prev_end, min(duration_ms, new_start))
            new_end = max(0, min(duration_ms, new_end))
            if new_end <= new_start:
                # Re-try keeping original end if snapping end collapsed onto snapped start.
                fallback_end = min(duration_ms, move.end_ms)
                if fallback_end - new_start >= _MIN_SNAPPED_PUNCH_MS:
                    new_end = fallback_end
                else:
                    continue
            if new_end - new_start < _MIN_SNAPPED_PUNCH_MS:
                continue
            held_scale = float(move.scale_end)
            snapped.append(
                CameraMove(
                    start_ms=new_start,
                    end_ms=new_end,
                    kind=move.kind,
                    scale_start=held_scale,
                    scale_end=held_scale,
                    reason=move.reason,
                )
            )
            prev_end = new_end
        elif move.kind == "slow_push":
            new_start = max(prev_end, move.start_ms)
            new_end = move.end_ms
            orig_dur = move.end_ms - move.start_ms
            if (
                snap_e := _nearest_cut_within(new_end, cuts, snap_window_ms)
            ) is not None and snap_e > new_start:
                # If snapping end forward lengthens the push, shift start forward by the
                # delta so moving-camera duration never grows beyond the 25% D-382 cap.
                if snap_e - new_start > orig_dur:
                    new_start = max(prev_end, snap_e - orig_dur)
                new_end = snap_e
            new_end = min(duration_ms, new_end)
            if new_end <= new_start:
                continue
            snapped.append(
                CameraMove(
                    start_ms=new_start,
                    end_ms=new_end,
                    kind="slow_push",
                    scale_start=float(move.scale_start),
                    scale_end=float(move.scale_end),
                    reason=move.reason,
                )
            )
            prev_end = new_end
        else:
            new_start = max(prev_end, move.start_ms)
            new_end = min(duration_ms, move.end_ms)
            if new_end <= new_start:
                continue
            snapped.append(
                CameraMove(
                    start_ms=new_start,
                    end_ms=new_end,
                    kind="locked",
                    scale_start=float(move.scale_start),
                    scale_end=float(move.scale_end),
                    reason=move.reason,
                )
            )
            prev_end = new_end

    return _validate_camera_moves(snapped, duration_ms=duration_ms)


def compile_restrained_camera_filter(
    duration_ms: int,
    camera_moves: Sequence[CameraMove],
    *,
    fps: float = 25.0,
    width: int = 1080,
    height: int = 1920,
    anchor_y: float = 0.33,
    cinema_grade: bool = True,
    shot_cuts_ms: Sequence[int] = (),
    jump_cuts_ms: Sequence[int] = (),
    ease_out_ms: int = SLOW_PUSH_EASE_OUT_MS,
) -> tuple[str, tuple[int, ...]]:
    """Compile validated ``CameraMove`` windows into a zero-sway FFmpeg filter (D-382, D-387).

    - Default is ``1.0000`` locked tripod with ``x='iw/2-(iw/zoom/2)'`` (zero ``sin(...)``).
    - Empty or all-``1.00×`` moves emit ONLY ``STUDIO_GRADE_FILTER`` with zero ``zoompan``.
    - ``punch_cut`` / ``wide_release`` cut **instantly** in 1 frame to ``scale_end`` and hold
      constant across ``[start_ms, end_ms]`` (zero ramp).
    - ``slow_push`` eases smoothly via cosine S-curve; when ending mid-shot (not within 50 ms
      of a real shot/jump cut, clip end, or adjacent move), appends a smooth ``ease_out_ms``
      (default 450 ms) cosine ease-out back to ``1.0000`` so it never hard-snaps mid-shot.
    """
    if _req_float(fps, "fps") <= 0.0:
        raise DirectorScriptError(f"fps must be > 0, got {fps}")
    _req_int(width, "width", min_value=2)
    _req_int(height, "height", min_value=2)
    _req_float(anchor_y, "anchor_y")
    _req_int(ease_out_ms, "ease_out_ms", min_value=0)

    sorted_moves = (
        snap_camera_moves_to_cuts(camera_moves, shot_cuts_ms, jump_cuts_ms, duration_ms)
        if (shot_cuts_ms or jump_cuts_ms)
        else _validate_camera_moves(camera_moves, duration_ms=duration_ms)
    )
    all_cuts = {int(c) for c in (*shot_cuts_ms, *jump_cuts_ms) if 0 < int(c) < duration_ms}

    raw_segs: list[tuple[int, int, float, float]] = []
    cursor = 0
    for idx, m in enumerate(sorted_moves):
        if m.start_ms > cursor:
            raw_segs.append((cursor, m.start_ms, 1.0, 1.0))
        if m.kind == "slow_push":
            z0, z1 = float(m.scale_start), float(m.scale_end)
        elif m.kind == "locked":
            z0 = z1 = float(m.scale_start)
        else:
            z0 = z1 = float(m.scale_end)
        raw_segs.append((m.start_ms, m.end_ms, z0, z1))
        cursor = m.end_ms

        if m.kind == "slow_push" and abs(z1 - 1.0) > CAMERA_MOTION_EPS and ease_out_ms > 0:
            next_start = (
                sorted_moves[idx + 1].start_ms if idx + 1 < len(sorted_moves) else duration_ms
            )
            on_real_cut = any(abs(m.end_ms - c) <= _CUT_ALIGN_TOLERANCE_MS for c in all_cuts)
            at_clip_end = m.end_ms >= duration_ms - _CUT_ALIGN_TOLERANCE_MS
            adjacent_next = (
                idx + 1 < len(sorted_moves) and next_start <= m.end_ms + _CUT_ALIGN_TOLERANCE_MS
            )
            if not on_real_cut and not at_clip_end and not adjacent_next:
                ret_end = min(m.end_ms + ease_out_ms, next_start, duration_ms)
                if ret_end > m.end_ms:
                    raw_segs.append((m.end_ms, ret_end, z1, 1.0))
                    cursor = ret_end
    if cursor < duration_ms:
        raw_segs.append((cursor, duration_ms, 1.0, 1.0))

    if all(abs(z0 - 1.0) < 1e-4 and abs(z1 - 1.0) < 1e-4 for _, _, z0, z1 in raw_segs):
        return (STUDIO_GRADE_FILTER if cinema_grade else "", ())

    segments: list[tuple[int, int, float, float]] = []
    for s0, s1, z0, z1 in raw_segs:
        if (
            segments
            and abs(segments[-1][3] - segments[-1][2]) < 1e-4
            and abs(z1 - z0) < 1e-4
            and abs(segments[-1][3] - z0) < 1e-4
        ):
            segments[-1] = (segments[-1][0], s1, segments[-1][2], z1)
        else:
            segments.append((s0, s1, z0, z1))

    jumps: list[int] = []
    exprs: list[str] = []
    end_frames: list[int] = []
    for idx, (s0, s1, z0, z1) in enumerate(segments):
        if idx > 0 and abs(z0 - segments[idx - 1][3]) >= _JUMP_CUT_DELTA_THRESHOLD:
            jumps.append(s0)
        f0 = round(s0 * fps / 1000.0)
        f1 = max(f0 + 1, round(s1 * fps / 1000.0))
        dz = z1 - z0
        if abs(dz) < 1e-4:
            expr = f"{z0:.4f}"
        else:
            sign = "+" if dz >= 0.0 else "-"
            expr = (
                f"{z0:.4f}{sign}{abs(dz):.4f}*(0.5-0.5*cos(PI*min(1,max(0,(in-{f0})/{f1 - f0}))))"
            )
        exprs.append(expr)
        end_frames.append(f1)

    z_expr = exprs[-1]
    for ef, expr in reversed(list(zip(end_frames[:-1], exprs[:-1], strict=True))):
        z_expr = f"if(lt(in,{ef}),{expr},{z_expr})"

    eff_y = max(0.24, min(0.46, float(anchor_y)))
    zp = (
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)'"
        f":y='ih*{eff_y:.3f}-(ih/zoom*{eff_y:.3f})':d=1:s={width}x{height}:fps={fps:g},setsar=1"
    )
    return (f"{zp},{STUDIO_GRADE_FILTER}" if cinema_grade else zp), tuple(jumps)
