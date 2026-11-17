"""Real pixel masks, not caption-band percentiles, define observed ink contrast."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from hawedit.measure import detect_caption_ink_in_band


@pytest.mark.parametrize("background,foreground", [(0, 255), (255, 0)])
def test_caption_stroke_contrast_is_linear_luminance_and_at_least_one(
    background: int,
    foreground: int,
) -> None:
    frame = np.full((1920, 1080, 3), background, dtype=np.uint8)
    cv2.putText(
        frame,
        "Synthetic",
        (220, 1550),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (foreground, foreground, foreground),
        5,
    )
    has_ink, contrast = detect_caption_ink_in_band(frame, 1248, 1824)
    assert has_ink is True
    assert contrast == pytest.approx(21.0, abs=0.01)


def test_uniform_black_band_does_not_claim_caption_ink_or_contrast() -> None:
    frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
    assert detect_caption_ink_in_band(frame, 1248, 1824) == (False, None)
