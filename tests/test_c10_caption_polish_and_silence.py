"""Tests for Lane C (D-358): clip-only Sorani caption polish & E3-safe dead-air tightening."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from hawedit.caption_polish import (
    CAPTION_POLISH_SCHEMA,
    CaptionPolishResult,
    deduplicate_micro_stutters,
    polish_clip_sentences,
)
from hawedit.captions import CaptionStyle
from hawedit.content_type import ContentType
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
    validate_edl,
)
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.silence import (
    KURDISH_FILLER_TOKENS,
    plan_silence_tightening,
    tighten_sentences,
    tighten_silence,
)
from hawedit.transcripts import Word


def _w(text: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


class _FakePolishClient:
    """Deterministic test double satisfying `StructuredJsonClient`."""

    model_id = "gemini-4-carbon"

    def __init__(self, response_text: str, *, wrap_envelope: bool = True) -> None:
        self._response_text = response_text
        self._wrap_envelope = wrap_envelope
        self.seen_parts: list[list[dict[str, Any]]] = []
        self.seen_schemas: list[Mapping[str, Any]] = []

    def count_parts(self, parts: list[dict[str, Any]]) -> int:
        return len(json.dumps(parts))

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
        self.seen_parts.append(parts)
        self.seen_schemas.append(schema)
        if not self._wrap_envelope:
            return self._response_text
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "internal reasoning"},
                                {"text": self._response_text},
                            ]
                        }
                    }
                ]
            }
        )


def _assert_no_additional_properties(obj: Any) -> None:
    if isinstance(obj, dict):
        assert "additionalProperties" not in obj
        for value in obj.values():
            _assert_no_additional_properties(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_additional_properties(item)


def test_deduplicate_micro_stutters_removes_ctc_stutter_preserving_emphatic_repeats() -> None:
    """AC-C1 / T5: Rapid CTC micro-stutters collapse; emphatic Kurdish repeats stay intact."""
    # Sentence 1 contains rapid CTC stutter `تۆپ تۆپ تۆپ` in 120..320 ms (each <= 120 ms)
    # and an intentional emphatic Kurdish repeat `زۆر زۆر` at 250 ms each (> 120 ms).
    s1 = Sentence(
        words=(
            _w("تۆپ", 120, 180, conf=0.72),
            _w("تۆپ", 185, 250, conf=0.81),
            _w("تۆپ", 255, 320, conf=0.88),
            _w("زۆر", 450, 700, conf=0.96),
            _w("زۆر", 740, 990, conf=0.97),
            _w("گرنگە.", 1040, 1400, conf=0.98),
        ),
        complete=True,
    )
    # Sentence 2 tests mixed-duration repeat (short + normal -> preserved) and punctuated stutter.
    s2 = Sentence(
        words=(
            _w("باشە", 2000, 2080, conf=0.80),  # 80 ms
            _w("باشە", 2100, 2360, conf=0.95),  # 260 ms (> 120 ms) -> NOT a micro-stutter
            _w("بڕۆ", 2500, 2570, conf=0.75),
            _w("بڕۆ.", 2580, 2650, conf=0.82),
        ),
        complete=False,
    )

    cleaned, removed = deduplicate_micro_stutters((s1, s2), max_token_ms=120)

    assert removed == 3  # 2 from تۆپ×3 + 1 from بڕۆ×2
    assert len(cleaned) == 2
    assert cleaned[0].complete is True
    assert cleaned[1].complete is False

    # Stutter collapsed to one token spanning full [120, 320] ms; emphatic `زۆر زۆر` untouched.
    assert [w.w for w in cleaned[0].words] == ["تۆپ", "زۆر", "زۆر", "گرنگە."]
    assert cleaned[0].words[0].start_ms == 120
    assert cleaned[0].words[0].end_ms == 320
    assert cleaned[0].words[0].conf == 0.88
    assert cleaned[0].words[1] == s1.words[3]
    assert cleaned[0].words[2] == s1.words[4]

    # Mixed-duration repeat preserved; punctuated micro-stutter retains trailing punctuation.
    assert [w.w for w in cleaned[1].words] == ["باشە", "باشە", "بڕۆ."]
    assert cleaned[1].words[2].start_ms == 2500
    assert cleaned[1].words[2].end_ms == 2650

    # Strictly monotone, deliverable order and original sentences untouched.
    assert_deliverable_order(cleaned)
    assert len(s1.words) == 6
    assert len(s2.words) == 4


def test_polish_clip_sentences_preserves_timestamps_and_rejects_hallucinations(
    tmp_path: Path,
) -> None:
    """AC-C1 / T5: 1-to-1 audio-grounded spelling fixes keep timestamps; hallucinations rejected."""
    _assert_no_additional_properties(CAPTION_POLISH_SCHEMA)

    original = (
        Sentence(
            words=(
                _w("تۆپ", 120, 180, conf=0.75),
                _w("تۆپ", 190, 250, conf=0.80),
                _w("تۆپ", 260, 320, conf=0.85),
                _w("ئەمڕۆ", 400, 800, conf=0.96),
                _w("چیت", 850, 1150, conf=0.84),
                _w("سکۆدس", 1200, 1650, conf=0.61),
                _w("لە", 1700, 1900, conf=0.98),
                _w("هەولێر", 1950, 2450, conf=0.97),
                _w("باس", 2500, 2850, conf=0.96),
                _w("دەکەین.", 2900, 3400, conf=0.98),
            ),
            complete=True,
        ),
    )

    # 1. client=None still deduplicates micro-stutters cleanly.
    offline = polish_clip_sentences(original, client=None)
    assert isinstance(offline, CaptionPolishResult)
    assert offline.applied is True
    assert offline.rejected_reason is None
    assert offline.stutters_removed == 2
    assert offline.words_polished == 0
    assert len(offline.sentences[0].words) == 8
    assert offline.sentences[0].words[0].start_ms == 120
    assert offline.sentences[0].words[0].end_ms == 320

    # 2. Valid 1-to-1 Sorani spelling fix with Gemini envelope and small inline WAV audio.
    wav_path = tmp_path / "clip.wav"
    wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
    wav_path.write_bytes(wav_bytes)

    good_client = _FakePolishClient(
        json.dumps({"replacements": [{"index": 3, "w": "کۆدز"}]}),
        wrap_envelope=True,
    )
    polished = polish_clip_sentences(original, client=good_client, audio_path=wav_path)
    assert polished.applied is True
    assert polished.rejected_reason is None
    assert polished.stutters_removed == 2
    assert polished.words_polished == 1
    assert len(good_client.seen_parts) == 1
    assert good_client.seen_schemas[0] == CAPTION_POLISH_SCHEMA

    # Inline WAV bytes were attached to the multimodal request parts.
    sent_parts = good_client.seen_parts[0]
    audio_parts = [p for p in sent_parts if "inlineData" in p]
    assert len(audio_parts) == 1
    assert audio_parts[0]["inlineData"]["mimeType"] == "audio/wav"
    assert base64.b64decode(audio_parts[0]["inlineData"]["data"]) == wav_bytes

    # Every timestamp, confidence, word count, and Sentence.complete is strictly preserved.
    assert len(polished.sentences) == len(offline.sentences)
    assert polished.sentences[0].complete is True
    assert [w.w for w in polished.sentences[0].words] == [
        "تۆپ",
        "ئەمڕۆ",
        "چیت",
        "کۆدز",
        "لە",
        "هەولێر",
        "باس",
        "دەکەین.",
    ]
    for before_w, after_w in zip(
        offline.sentences[0].words, polished.sentences[0].words, strict=True
    ):
        assert after_w.start_ms == before_w.start_ms
        assert after_w.end_ms == before_w.end_ms
        assert after_w.conf == before_w.conf
    # Original input sentences remain completely immutable.
    assert original[0].words[5].w == "سکۆدس"

    # 3. Reject empty replacement.
    empty_client = _FakePolishClient(json.dumps({"replacements": [{"index": 3, "w": "   "}]}))
    empty_res = polish_clip_sentences(original, client=empty_client)
    assert empty_res.applied is False
    assert empty_res.words_polished == 0
    assert empty_res.rejected_reason is not None and "empty" in empty_res.rejected_reason
    assert empty_res.sentences == offline.sentences

    # 4. Reject multi-word insertion (word-count mutation guardrail).
    split_client = _FakePolishClient(
        json.dumps({"replacements": [{"index": 3, "w": "کۆدز و پرۆگرام"}]})
    )
    split_res = polish_clip_sentences(original, client=split_client)
    assert split_res.applied is False
    assert split_res.words_polished == 0
    assert split_res.rejected_reason is not None and "whitespace" in split_res.rejected_reason
    assert split_res.sentences == offline.sentences

    # 5. Reject hallucination exceeding max_char_divergence (0.25).
    hallucination_client = _FakePolishClient(
        json.dumps(
            {
                "replacements": [
                    {"index": 0, "w": "سڵاو"},
                    {"index": 1, "w": "بەخێربێن"},
                    {"index": 2, "w": "بۆ"},
                    {"index": 3, "w": "کەناڵەکەمان"},
                    {"index": 4, "w": "سەبسکرایب"},
                    {"index": 5, "w": "بکەن"},
                ]
            }
        )
    )
    hallucination_res = polish_clip_sentences(
        original,
        client=hallucination_client,
        max_char_divergence=0.25,
    )
    assert hallucination_res.applied is False
    assert hallucination_res.words_polished == 0
    assert (
        hallucination_res.rejected_reason is not None
        and "divergence" in hallucination_res.rejected_reason
    )
    assert hallucination_res.sentences == offline.sentences
    assert hallucination_res.stutters_removed == 2

    # 6. Reject out-of-range index and malformed JSON cleanly.
    oob_client = _FakePolishClient(json.dumps({"replacements": [{"index": 99, "w": "کۆدز"}]}))
    oob_res = polish_clip_sentences(original, client=oob_client)
    assert oob_res.applied is False
    assert oob_res.sentences == offline.sentences

    bad_json_client = _FakePolishClient("not-valid-json", wrap_envelope=False)
    bad_json_res = polish_clip_sentences(original, client=bad_json_client)
    assert bad_json_res.applied is False
    assert bad_json_res.sentences == offline.sentences

    # 7. Invalid max_char_divergence fails fast.
    with pytest.raises(ValueError, match="max_char_divergence"):
        polish_clip_sentences(original, max_char_divergence=1.5)


def test_dead_air_tightening_preserves_kurdish_repeats_and_clears_e3_edl() -> None:
    """AC-C2 / T6: Pure dead-air tightening keeps Kurdish repeats & clears E3 validate_edl."""
    # Realistic 38-second Kurdish clip containing:
    # - Emphatic repeat: `زۆر زۆر` (10 ms gap — would trigger detect_restarts if wrongly enabled)
    # - Morphological prefix pair: `کورد` -> `کوردستان` (40 ms gap — would trigger false-start!)
    # - Two long dead-air pauses (> 1100 ms): 4000..5800 (1800 ms) and 18000..20200 (2200 ms)
    clip_in_ms = 900
    clip_out_ms = 39_100
    words = (
        _w("ئەم", 1000, 1400),
        _w("بابەتە", 1450, 2000),
        _w("زۆر", 2050, 2350),
        _w("زۆر", 2360, 2680),  # emphatic repeat, 10 ms gap
        _w("گرنگە", 2720, 3200),
        _w("بۆ", 3250, 3500),
        _w("کورد", 3520, 3720),
        _w("کوردستان", 3760, 4000),  # prefix pair, 40 ms gap
        # Dead-air pause #1: 4000..5800 (1800 ms > 1100 ms)
        _w("ئێمە", 5800, 6400),
        _w("بەردەوام", 6500, 12_000),
        _w("کار", 12_100, 18_000),
        # Dead-air pause #2: 18000..20200 (2200 ms > 1100 ms)
        _w("دەکەین", 20_200, 29_000),
        _w("تاکو", 29_100, 32_000),
        _w("تاکو", 32_020, 35_000),  # second emphatic repeat, 20 ms gap
        _w("سەردەکەوین.", 35_100, 39_000),
    )
    sentences = (
        Sentence(words=words[:8], complete=True),
        Sentence(words=words[8:11], complete=True),
        Sentence(words=words[11:], complete=True),
    )

    for target_gap in (300, 500, 20):
        plan = plan_silence_tightening(
            words,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            threshold_ms=1100,
            target_gap_ms=target_gap,
            filler_tokens=None,
        )
        # Zero restarts/fillers excised when filler_tokens=None.
        assert plan.excised_word_count == 0
        # Exactly the 2 dead-air pauses were cut -> 3 retained segments.
        assert len(plan.removed_intervals_ms) == 2
        assert len(plan.retained_intervals_ms) == 3

        # Every internal cut edge keeps [30, 200] ms padding from adjacent words.
        abs_retained = tuple(
            (clip_in_ms + s, clip_in_ms + e) for s, e in plan.retained_intervals_ms
        )
        seg0_end = abs_retained[0][1]
        seg1_start, seg1_end = abs_retained[1]
        seg2_start = abs_retained[2][0]
        assert 30 <= seg0_end - 4000 <= 200
        assert 30 <= 5800 - seg1_start <= 200
        assert 30 <= seg1_end - 18_000 <= 200
        assert 30 <= 20_200 - seg2_start <= 200

        # Full E3 hard edit rule validation passes with zero violations.
        dur = sum(e - s for s, e in abs_retained)
        edl_plan = VisualEditPlan(
            version=CURRENT_PLAN_VERSION,
            clip_id=f"c10-dead-air-{target_gap}",
            media_id="media_c10",
            media_sha256="b" * 64,
            brief=EditorialBrief(
                viewer_takeaway="تێستی بڕینی بێدەنگی بە پاراستنی دووبارەبوونەوەی کوردی",
                content_type=ContentType.PODCAST,
                target_duration_ms=(30_000, max(30_000, dur)),
            ),
            config=EffectiveConfiguration.resolve(
                content_type=ContentType.PODCAST,
                caption_style=CaptionStyle.WORD_HIGHLIGHT,
                silence_threshold_ms=1100,
                silence_target_gap_ms=target_gap,
            ),
            time_mapping=SourceTimeMapping(
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                retained_intervals_ms=abs_retained,
            ),
            sentences=sentences,
        )
        edl_result = validate_edl(edl_plan, words=words)
        assert edl_result.is_valid is True
        assert edl_result.violations == ()

    # tighten_silence and tighten_sentences with filler_tokens=None preserve all 15 words.
    tight_words, removed_ms = tighten_silence(
        words,
        threshold_ms=1100,
        target_gap_ms=300,
        filler_tokens=None,
    )
    assert removed_ms == (1800 - 300) + (2200 - 300)
    assert [w.w for w in tight_words] == [w.w for w in words]

    tight_sents, sent_removed_ms = tighten_sentences(
        sentences,
        threshold_ms=1100,
        target_gap_ms=300,
        filler_tokens=None,
    )
    assert sent_removed_ms == removed_ms
    assert [w.w for s in tight_sents for w in s.words] == [w.w for w in words]

    # Explicit restart removal uses its own opt-in and a marked partial token.
    # The original meaningful prefix/repeat words above remain preserved by default.
    from dataclasses import replace

    restart_words = tuple(replace(word, w="کورد-") if word.w == "کورد" else word for word in words)
    explicit_plan = plan_silence_tightening(
        restart_words,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=1100,
        target_gap_ms=300,
        filler_tokens=KURDISH_FILLER_TOKENS,
        detect_restarts=True,
    )
    assert explicit_plan.excised_word_count >= 3
