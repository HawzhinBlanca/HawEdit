"""HawEdit V9 Module A — Multi-Client Brand Kits & Curated Subtitle Style Presets (D-388).

Defines 5 agency-grade vertical-reel subtitle & brand-kit style presets:
- ``viral_gold`` (default): Studio Gold active pill + Electric Lime power beats.
- ``crimson_punch``: Bold TikTok Crimson active pill + crisp white ink + Gold power beats.
- ``executive_cyan``: High-clarity Tech Cyan active pill + deep navy frosted cards.
- ``luxury_minimal``: Obsidian frosted pill + champagne-gold ink & 2 px hairline border.
- ``broadcast_news``: Authoritative deep-navy broadcast pill + gold trim + locked camera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Final

__all__ = [
    "CLIENT_STYLE_PRESETS",
    "DEFAULT_STYLE_PRESET_NAME",
    "ClientStylePreset",
    "get_client_style_preset",
    "hex_to_rgb",
    "list_client_style_presets",
    "pick_contrasting_ink",
    "resolve_client_style_preset",
    "validate_hex_color",
    "wcag_contrast_ratio",
]

DEFAULT_STYLE_PRESET_NAME: Final[str] = "viral_gold"
_HEX_COLOR_RE: Final = re.compile(r"^#[0-9A-Fa-f]{6}$")


def validate_hex_color(value: str, *, field_name: str = "hex color") -> str:
    """Strictly validate a ``#RRGGBB`` hex color string and return uppercase form."""
    if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
        raise ValueError(f"{field_name} must be a strict #RRGGBB hex color, got {value!r}")
    return value.upper()


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a validated ``#RRGGBB`` string into an ``(r, g, b)`` integer tuple."""
    norm = validate_hex_color(hex_color)
    return (int(norm[1:3], 16), int(norm[3:5], 16), int(norm[5:7], 16))


def _relative_luminance(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)
    lin = [
        (c / 255.0) / 12.92 if (c / 255.0) <= 0.04045 else (((c / 255.0) + 0.055) / 1.055) ** 2.4
        for c in (r, g, b)
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def wcag_contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute the WCAG 2.1 contrast ratio (1.0..21.0) between two ``#RRGGBB`` colors."""
    l1 = _relative_luminance(fg_hex)
    l2 = _relative_luminance(bg_hex)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def pick_contrasting_ink(
    bg_hex: str, *, dark_hex: str = "#0B0B0F", light_hex: str = "#FFFFFF"
) -> str:
    """Return ``dark_hex`` or ``light_hex``, whichever yields higher WCAG contrast on ``bg_hex``."""
    dark_norm = validate_hex_color(dark_hex, field_name="dark_hex")
    light_norm = validate_hex_color(light_hex, field_name="light_hex")
    bg_norm = validate_hex_color(bg_hex, field_name="bg_hex")
    return (
        dark_norm
        if wcag_contrast_ratio(dark_norm, bg_norm) >= wcag_contrast_ratio(light_norm, bg_norm)
        else light_norm
    )


def _validate_rgba(rgba: tuple[int, int, int, int], *, field_name: str) -> None:
    if len(rgba) != 4 or not all(isinstance(v, int) and 0 <= v <= 255 for v in rgba):
        raise ValueError(f"{field_name} must be 4 ints in 0..255, got {rgba!r}")


@dataclass(frozen=True, slots=True)
class ClientStylePreset:
    """Immutable visual brand kit & subtitle style preset for V8/V9 vertical reels."""

    name: str
    display_name: str
    description: str
    active_pill_hex: str
    active_pill_alpha: int
    active_text_hex: str
    active_pill_border_hex: str | None
    active_pill_border_width_px: float
    active_pill_border_alpha: int
    power_pill_hex: str
    power_text_hex: str
    inactive_text_hex: str
    inactive_outline_hex: str
    hook_fill_rgba: tuple[int, int, int, int]
    hook_border_hex: str
    hook_border_alpha: int
    interrupt_fill_rgba: tuple[int, int, int, int]
    interrupt_top_border_hex: str
    interrupt_chest_border_hex: str
    progress_bar_hex: str
    allow_camera_moves: bool
    max_camera_scale: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("preset name must be non-empty")
        if not self.display_name.strip():
            raise ValueError("preset display_name must be non-empty")
        if not self.description.strip():
            raise ValueError("preset description must be non-empty")
        for attr in (
            "active_pill_hex",
            "active_text_hex",
            "power_pill_hex",
            "power_text_hex",
            "inactive_text_hex",
            "inactive_outline_hex",
            "hook_border_hex",
            "interrupt_top_border_hex",
            "interrupt_chest_border_hex",
            "progress_bar_hex",
        ):
            validate_hex_color(getattr(self, attr), field_name=attr)
        if self.active_pill_border_hex is not None:
            validate_hex_color(self.active_pill_border_hex, field_name="active_pill_border_hex")
        for alpha_attr in ("active_pill_alpha", "active_pill_border_alpha", "hook_border_alpha"):
            val = getattr(self, alpha_attr)
            if not isinstance(val, int) or not 0 <= val <= 255:
                raise ValueError(f"{alpha_attr} must be an int in 0..255, got {val!r}")
        if self.active_pill_border_width_px < 0.0:
            raise ValueError(
                f"active_pill_border_width_px must be >= 0, got {self.active_pill_border_width_px}"
            )
        _validate_rgba(self.hook_fill_rgba, field_name="hook_fill_rgba")
        _validate_rgba(self.interrupt_fill_rgba, field_name="interrupt_fill_rgba")
        if not 1.0 <= self.max_camera_scale <= 1.25:
            raise ValueError(
                f"max_camera_scale must lie in [1.0, 1.25], got {self.max_camera_scale}"
            )
        if not self.allow_camera_moves and self.max_camera_scale != 1.0:
            raise ValueError(
                "max_camera_scale must be 1.00 when allow_camera_moves is False, "
                f"got {self.max_camera_scale}"
            )

    @property
    def accent_hex(self) -> str:
        """Primary visible brand accent hex (border on dark-pill styles, pill hex otherwise)."""
        return (
            self.active_pill_border_hex
            if self.active_pill_border_hex is not None
            else self.active_pill_hex
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize preset metadata and color swatches for Studio Web API / JSON manifests."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "active_pill_hex": self.active_pill_hex,
            "active_pill_alpha": self.active_pill_alpha,
            "active_text_hex": self.active_text_hex,
            "active_pill_border_hex": self.active_pill_border_hex,
            "power_pill_hex": self.power_pill_hex,
            "power_text_hex": self.power_text_hex,
            "inactive_text_hex": self.inactive_text_hex,
            "hook_border_hex": self.hook_border_hex,
            "progress_bar_hex": self.progress_bar_hex,
            "allow_camera_moves": self.allow_camera_moves,
            "max_camera_scale": self.max_camera_scale,
            "swatches": [self.active_pill_hex, self.power_pill_hex, self.progress_bar_hex],
            "active_contrast_ratio": round(
                wcag_contrast_ratio(self.active_text_hex, self.active_pill_hex), 2
            ),
        }


CLIENT_STYLE_PRESETS: Final[dict[str, ClientStylePreset]] = {
    "viral_gold": ClientStylePreset(
        name="viral_gold",
        display_name="Viral Gold",
        description="Studio Gold active pill, Electric Lime power beats, punchy dynamic camera.",
        active_pill_hex="#FFD700",
        active_pill_alpha=255,
        active_text_hex="#0B0B0F",
        active_pill_border_hex=None,
        active_pill_border_width_px=2.0,
        active_pill_border_alpha=75,
        power_pill_hex="#B8FF2E",
        power_text_hex="#0B0B0F",
        inactive_text_hex="#FFFFFF",
        inactive_outline_hex="#0B0B0F",
        hook_fill_rgba=(11, 11, 15, 205),
        hook_border_hex="#FFD700",
        hook_border_alpha=165,
        interrupt_fill_rgba=(15, 18, 28, 220),
        interrupt_top_border_hex="#B8FF2E",
        interrupt_chest_border_hex="#FFD700",
        progress_bar_hex="#FFD700",
        allow_camera_moves=True,
        max_camera_scale=1.14,
    ),
    "crimson_punch": ClientStylePreset(
        name="crimson_punch",
        display_name="Crimson Punch",
        description="Bold Crimson pill with crisp white ink, Gold power beats, energetic camera.",
        active_pill_hex="#FF2E63",
        active_pill_alpha=255,
        active_text_hex="#FFFFFF",
        active_pill_border_hex=None,
        active_pill_border_width_px=2.0,
        active_pill_border_alpha=95,
        power_pill_hex="#FFD700",
        power_text_hex="#0B0B0F",
        inactive_text_hex="#FFFFFF",
        inactive_outline_hex="#0B0B0F",
        hook_fill_rgba=(16, 10, 16, 215),
        hook_border_hex="#FF2E63",
        hook_border_alpha=225,
        interrupt_fill_rgba=(18, 12, 18, 225),
        interrupt_top_border_hex="#FF2E63",
        interrupt_chest_border_hex="#FF2E63",
        progress_bar_hex="#FF2E63",
        allow_camera_moves=True,
        max_camera_scale=1.15,
    ),
    "executive_cyan": ClientStylePreset(
        name="executive_cyan",
        display_name="Executive Cyan",
        description="Clean Tech Cyan pill, pure white power beats, deep navy frosted cards.",
        active_pill_hex="#00D4FF",
        active_pill_alpha=255,
        active_text_hex="#07131C",
        active_pill_border_hex=None,
        active_pill_border_width_px=2.0,
        active_pill_border_alpha=90,
        power_pill_hex="#FFFFFF",
        power_text_hex="#07131C",
        inactive_text_hex="#FFFFFF",
        inactive_outline_hex="#07131C",
        hook_fill_rgba=(11, 18, 32, 230),
        hook_border_hex="#00D4FF",
        hook_border_alpha=230,
        interrupt_fill_rgba=(11, 18, 32, 230),
        interrupt_top_border_hex="#00D4FF",
        interrupt_chest_border_hex="#00D4FF",
        progress_bar_hex="#00D4FF",
        allow_camera_moves=True,
        max_camera_scale=1.08,
    ),
    "luxury_minimal": ClientStylePreset(
        name="luxury_minimal",
        display_name="Luxury Minimal",
        description="Obsidian dark-glass active pill, champagne-gold ink, and 2 px hairline trim.",
        active_pill_hex="#161820",
        active_pill_alpha=235,
        active_text_hex="#F5C451",
        active_pill_border_hex="#F5C451",
        active_pill_border_width_px=2.0,
        active_pill_border_alpha=245,
        power_pill_hex="#F5C451",
        power_text_hex="#111216",
        inactive_text_hex="#FFFFFF",
        inactive_outline_hex="#111216",
        hook_fill_rgba=(18, 20, 26, 230),
        hook_border_hex="#F5C451",
        hook_border_alpha=230,
        interrupt_fill_rgba=(18, 20, 26, 230),
        interrupt_top_border_hex="#F5C451",
        interrupt_chest_border_hex="#F5C451",
        progress_bar_hex="#F5C451",
        allow_camera_moves=True,
        max_camera_scale=1.08,
    ),
    "broadcast_news": ClientStylePreset(
        name="broadcast_news",
        display_name="Broadcast News",
        description="Deep-navy broadcast pill with gold trim, crisp white ink, locked camera.",
        active_pill_hex="#102446",
        active_pill_alpha=240,
        active_text_hex="#FFFFFF",
        active_pill_border_hex="#FFD700",
        active_pill_border_width_px=2.5,
        active_pill_border_alpha=245,
        power_pill_hex="#FFD700",
        power_text_hex="#0B1220",
        inactive_text_hex="#FFFFFF",
        inactive_outline_hex="#0B1220",
        hook_fill_rgba=(16, 36, 70, 235),
        hook_border_hex="#FFD700",
        hook_border_alpha=240,
        interrupt_fill_rgba=(16, 36, 70, 235),
        interrupt_top_border_hex="#FFD700",
        interrupt_chest_border_hex="#FFD700",
        progress_bar_hex="#1D4ED8",
        allow_camera_moves=False,
        max_camera_scale=1.00,
    ),
}


def get_client_style_preset(
    name: str, *, accent_hex_override: str | None = None
) -> ClientStylePreset:
    """Look up a curated :class:`ClientStylePreset` by name with optional brand accent override."""
    if not isinstance(name, str) or name not in CLIENT_STYLE_PRESETS:
        valid = ", ".join(CLIENT_STYLE_PRESETS)
        raise ValueError(f"unknown style preset {name!r}; expected one of: {valid}")
    preset = CLIENT_STYLE_PRESETS[name]
    if accent_hex_override is None:
        return preset

    accent = validate_hex_color(accent_hex_override, field_name="accent_hex_override")
    top_border = (
        accent
        if preset.interrupt_top_border_hex == preset.hook_border_hex
        else preset.interrupt_top_border_hex
    )
    if preset.active_pill_border_hex is None:
        # Bright-pill style: override pill fill + auto-select highest-contrast ink.
        return replace(
            preset,
            active_pill_hex=accent,
            active_text_hex=pick_contrasting_ink(accent),
            hook_border_hex=accent,
            interrupt_top_border_hex=top_border,
            interrupt_chest_border_hex=accent,
            progress_bar_hex=accent,
        )

    # Dark-pill framed style (luxury_minimal / broadcast_news): preserve dark pill readability
    # and apply client accent to trim, borders, progress bar, and (when high-contrast) gold ink.
    new_active_text = preset.active_text_hex
    if preset.active_text_hex == preset.active_pill_border_hex:
        new_active_text = (
            accent if wcag_contrast_ratio(accent, preset.active_pill_hex) >= 4.5 else "#FFFFFF"
        )
    return replace(
        preset,
        active_text_hex=new_active_text,
        active_pill_border_hex=accent,
        hook_border_hex=accent,
        interrupt_top_border_hex=top_border,
        interrupt_chest_border_hex=accent,
        progress_bar_hex=accent,
    )


def resolve_client_style_preset(preset: ClientStylePreset | str | None) -> ClientStylePreset:
    """Resolve ``None``, a preset name, or a :class:`ClientStylePreset` fail-stop."""
    if preset is None:
        return CLIENT_STYLE_PRESETS[DEFAULT_STYLE_PRESET_NAME]
    if isinstance(preset, ClientStylePreset):
        return preset
    if isinstance(preset, str):
        return get_client_style_preset(preset)
    raise TypeError(
        f"style_preset must be ClientStylePreset, str, or None, got {type(preset).__name__}"
    )


def list_client_style_presets() -> tuple[dict[str, Any], ...]:
    """Return JSON-ready metadata & swatch dictionaries for all 5 curated client presets."""
    return tuple(preset.to_dict() for preset in CLIENT_STYLE_PRESETS.values())
