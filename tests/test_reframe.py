from __future__ import annotations

from pathlib import Path

from hawedit.reframe import OpenCvFaceTracker, choose_face

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def test_face_choice_prefers_area_then_preserves_subject_continuity() -> None:
    near = (90, 10, 50, 50)
    far = (500, 10, 100, 100)
    assert choose_face((near, far), previous_x=None) == far
    assert choose_face((near, far), previous_x=115) == near


def test_face_tracker_runs_on_real_media_and_reports_no_invented_subject() -> None:
    # The fixture contains only large digits, not faces. Empty is evidence that no face was
    # detected; fabricating a centre point here would make a static shot look tracked.
    assert OpenCvFaceTracker(sample_fps=2.0).track(FIXTURE, 0, 1_000) == ()
