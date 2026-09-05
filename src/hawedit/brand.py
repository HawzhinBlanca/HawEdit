"""Brand Kit configuration and video branding overlays (Task T2.13, ADR D-268).

Provides structured branding assets and automated filter generation for:
1. Lower-third speaker labels (from episode metadata mapped to diarization labels).
2. Logo watermark overlay with position, opacity, and margin controls.
3. Animated retention progress bar advancing across reel playback.
4. 2-second outro end card with Kurdish call-to-action and channel handle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DEFAULT_LOGO_MARGIN",
    "DEFAULT_LOGO_OPACITY",
    "DEFAULT_LOGO_WIDTH",
    "DEFAULT_PROGRESS_BAR_COLOR",
    "DEFAULT_PROGRESS_BAR_HEIGHT",
    "BrandKit",
    "BrandKitError",
    "EndCardConfig",
    "ProgressBarConfig",
    "SpeakerBio",
    "logo_overlay_coordinates",
    "progress_bar_filter",
]

DEFAULT_LOGO_WIDTH: Final[int] = 160
DEFAULT_LOGO_OPACITY: Final[float] = 0.85
DEFAULT_LOGO_MARGIN: Final[int] = 40
DEFAULT_PROGRESS_BAR_COLOR: Final[str] = "#E50914"
DEFAULT_PROGRESS_BAR_HEIGHT: Final[int] = 6

_VALID_POSITIONS: Final[frozenset[str]] = frozenset(
    {"top_right", "top_left", "bottom_right", "bottom_left"}
)


class BrandKitError(Exception):
    """Raised when a brand kit configuration or asset validation fails."""


@dataclass(frozen=True, slots=True)
class SpeakerBio:
    """Speaker identity metadata for lower-third introduction tags."""

    name_ckb: str
    title_ckb: str | None = None

    def __post_init__(self) -> None:
        if not self.name_ckb or not self.name_ckb.strip():
            raise ValueError("name_ckb must not be empty")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name_ckb": self.name_ckb}
        if self.title_ckb is not None:
            data["title_ckb"] = self.title_ckb
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeakerBio:
        if not isinstance(data, dict):
            raise TypeError("SpeakerBio data must be a dictionary")
        name = data.get("name_ckb") or data.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("SpeakerBio requires a non-empty string name_ckb")
        title = data.get("title_ckb") or data.get("title")
        return cls(name_ckb=name.strip(), title_ckb=title.strip() if title else None)


@dataclass(frozen=True, slots=True)
class ProgressBarConfig:
    """Configuration for dynamic viewer retention progress bar."""

    enabled: bool = False
    color: str = DEFAULT_PROGRESS_BAR_COLOR
    height_px: int = DEFAULT_PROGRESS_BAR_HEIGHT
    position: str = "bottom"

    def __post_init__(self) -> None:
        if self.height_px <= 0:
            raise ValueError(f"height_px must be positive, got {self.height_px}")
        if self.position not in ("bottom", "top"):
            raise ValueError(f"position must be 'bottom' or 'top', got {self.position!r}")
        if not self.color or not self.color.strip():
            raise ValueError("color must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "color": self.color,
            "height_px": self.height_px,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressBarConfig:
        if not isinstance(data, dict):
            raise TypeError("ProgressBarConfig data must be a dictionary")
        return cls(
            enabled=bool(data.get("enabled", False)),
            color=str(data.get("color", DEFAULT_PROGRESS_BAR_COLOR)),
            height_px=int(data.get("height_px", DEFAULT_PROGRESS_BAR_HEIGHT)),
            position=str(data.get("position", "bottom")),
        )


@dataclass(frozen=True, slots=True)
class EndCardConfig:
    """Configuration for 2-second outro card with call-to-action."""

    enabled: bool = False
    duration_s: float = 2.0
    title_ckb: str | None = None
    subtitle_ckb: str | None = None
    handle: str | None = None
    background_color: str = "#000000"

    def __post_init__(self) -> None:
        if self.duration_s <= 0.0:
            raise ValueError(f"duration_s must be positive, got {self.duration_s}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "duration_s": self.duration_s,
            "title_ckb": self.title_ckb,
            "subtitle_ckb": self.subtitle_ckb,
            "handle": self.handle,
            "background_color": self.background_color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndCardConfig:
        if not isinstance(data, dict):
            raise TypeError("EndCardConfig data must be a dictionary")
        return cls(
            enabled=bool(data.get("enabled", False)),
            duration_s=float(data.get("duration_s", 2.0)),
            title_ckb=data.get("title_ckb"),
            subtitle_ckb=data.get("subtitle_ckb"),
            handle=data.get("handle"),
            background_color=str(data.get("background_color", "#000000")),
        )


@dataclass(frozen=True, slots=True)
class BrandKit:
    """Comprehensive branding specifications for a video reel."""

    speaker_metadata: dict[str, SpeakerBio] = field(default_factory=dict)
    logo_path: Path | None = None
    logo_position: str = "top_right"
    logo_width: int = DEFAULT_LOGO_WIDTH
    logo_opacity: float = DEFAULT_LOGO_OPACITY
    logo_margin: int = DEFAULT_LOGO_MARGIN
    progress_bar: ProgressBarConfig = field(default_factory=ProgressBarConfig)
    end_card: EndCardConfig = field(default_factory=EndCardConfig)

    def __post_init__(self) -> None:
        if self.logo_width <= 0:
            raise ValueError(f"logo_width must be positive, got {self.logo_width}")
        if not (0.0 < self.logo_opacity <= 1.0):
            raise ValueError(f"logo_opacity must be in (0.0, 1.0], got {self.logo_opacity}")
        if self.logo_margin < 0:
            raise ValueError(f"logo_margin must be non-negative, got {self.logo_margin}")
        if self.logo_position not in _VALID_POSITIONS:
            raise ValueError(
                f"invalid logo_position: {self.logo_position!r}; expected one of {_VALID_POSITIONS}"
            )

    def assert_valid(self) -> None:
        """Validate assets presence, raising BrandKitError on missing files."""
        if self.logo_path is not None:
            if not self.logo_path.exists():
                raise BrandKitError(f"brand logo file not found: {self.logo_path}")
            if not self.logo_path.is_file():
                raise BrandKitError(f"brand logo path is not a file: {self.logo_path}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_metadata": {spk: bio.to_dict() for spk, bio in self.speaker_metadata.items()},
            "logo_path": str(self.logo_path) if self.logo_path is not None else None,
            "logo_position": self.logo_position,
            "logo_width": self.logo_width,
            "logo_opacity": self.logo_opacity,
            "logo_margin": self.logo_margin,
            "progress_bar": self.progress_bar.to_dict(),
            "end_card": self.end_card.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, base_dir: Path | None = None) -> BrandKit:
        if not isinstance(data, dict):
            raise TypeError("BrandKit data must be a dictionary")

        speakers: dict[str, SpeakerBio] = {}
        raw_speakers = data.get("speaker_metadata") or data.get("speakers") or {}
        if isinstance(raw_speakers, dict):
            for spk_key, spk_val in raw_speakers.items():
                if isinstance(spk_val, dict):
                    speakers[spk_key] = SpeakerBio.from_dict(spk_val)
                elif isinstance(spk_val, str):
                    speakers[spk_key] = SpeakerBio(name_ckb=spk_val.strip())

        raw_logo = data.get("logo_path") or data.get("logo")
        logo_path: Path | None = None
        if raw_logo:
            p = Path(str(raw_logo))
            if not p.is_absolute() and base_dir is not None:
                p = base_dir / p
            logo_path = p

        progress = ProgressBarConfig.from_dict(data.get("progress_bar", {}))
        end_card = EndCardConfig.from_dict(data.get("end_card", {}))

        return cls(
            speaker_metadata=speakers,
            logo_path=logo_path,
            logo_position=str(data.get("logo_position", "top_right")),
            logo_width=int(data.get("logo_width", DEFAULT_LOGO_WIDTH)),
            logo_opacity=float(data.get("logo_opacity", DEFAULT_LOGO_OPACITY)),
            logo_margin=int(data.get("logo_margin", DEFAULT_LOGO_MARGIN)),
            progress_bar=progress,
            end_card=end_card,
        )

    @classmethod
    def from_json(cls, path: Path) -> BrandKit:
        if not path.exists():
            raise BrandKitError(f"brand kit config file does not exist: {path}")
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BrandKitError(f"failed to parse brand kit JSON from {path}: {exc}") from exc
        kit = cls.from_dict(content, base_dir=path.parent)
        kit.assert_valid()
        return kit


def logo_overlay_coordinates(position: str, margin: int = DEFAULT_LOGO_MARGIN) -> tuple[str, str]:
    """Compute FFmpeg overlay (x, y) expression strings for canvas corners."""
    if position == "top_right":
        return f"main_w-overlay_w-{margin}", str(margin)
    if position == "top_left":
        return str(margin), str(margin)
    if position == "bottom_right":
        return f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"
    if position == "bottom_left":
        return str(margin), f"main_h-overlay_h-{margin}"
    raise ValueError(f"unsupported position: {position!r}")


def progress_bar_filter(
    duration_s: float,
    color: str = DEFAULT_PROGRESS_BAR_COLOR,
    height_px: int = DEFAULT_PROGRESS_BAR_HEIGHT,
    position: str = "bottom",
    canvas_height: int = 1920,
) -> str:
    """Generate FFmpeg drawbox filter for dynamic playback progress bar."""
    if duration_s <= 0.0:
        raise ValueError(f"duration_s must be positive, got {duration_s}")
    if height_px <= 0:
        raise ValueError(f"height_px must be positive, got {height_px}")
    y = canvas_height - height_px if position == "bottom" else 0
    return (
        f"drawbox=x=0:y={y}:w='iw*min(t/{duration_s:.3f},1.0)':h={height_px}:color={color}:t=fill"
    )
