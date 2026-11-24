"""Focused offline/mocked unit & contract tests for HawEdit V10.2 (D-394).

Covers:
1. Non-contiguous MultiCutStoryRecipe assembly + drop_ranges subtraction + gemini-4-carbon
   meaning-preservation surgical rollback.
2. 16 kHz acoustic prosody RMS-valley snapping (never clips voiced consonants) + equal-power
   quarter-sine splice crossfades in assembly.py.
3. Visual-aware shot-scale profiling, dual-speaker banter 50/50 split-screen detection,
   negative-space overlay routing, and mid-sentence jump-cut cover choreography.
4. B-roll semantic verification threshold gate (< 0.26 hard reject, >= 0.26 accept), NonCommercial
   license refusal, provenance sidecars, and fullscreen/top_pip/Ken Burns FFmpeg clauses.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

import pytest

from hawedit.assembly import AssemblySpan, assembled_splice_filter
from hawedit.render import BRollItem, assert_asset_provenance, build_broll_overlay_clause
from hawedit.sentences import Sentence
from hawedit.silence import KURDISH_FILLER_TOKENS
from hawedit.transcripts import Word
from hawedit.v8.asd import ActiveSpeakerScore, FaceDetectionFrame, LockedShotCrop
from hawedit.v8.broll import (
    BRollError,
    cosine_similarity,
    resolve_visual_cues_to_broll,
    verify_broll_relevance,
    write_asset_provenance,
)
from hawedit.v8.story_editor import (
    VisualCue,
    compile_story_to_assembly_spans,
    plan_episode_multicut_stories,
    snap_cut_to_rms_valley,
    verify_story_meaning_preservation,
)
from hawedit.v8.visual_aware import (
    CutCoverAction,
    ShotVisualProfile,
    VisualGroundings,
    analyze_shot_visual_profiles,
    apply_visual_groundings_to_profiles,
    choreograph_cut_covers,
    compute_two_person_split_crops,
    protect_visual_gestures_in_cuts,
)


def _make_words(tokens: list[str], *, step_ms: int = 400, gap_ms: int = 80) -> tuple[Word, ...]:
    words: list[Word] = []
    t = 1000
    for tok in tokens:
        words.append(Word(w=tok, start_ms=t, end_ms=t + step_ms, conf=0.95))
        t += step_ms + gap_ms
    return tuple(words)


def _write_test_wav(path: Path, samples: list[int], sr: int = 16_000) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def test_kurdish_filler_tokens_include_spoken_yani() -> None:
    assert "یانی" in KURDISH_FILLER_TOKENS
    assert "یانى" in KURDISH_FILLER_TOKENS
    assert "بە هەر حاڵ" in KURDISH_FILLER_TOKENS


def test_multicut_story_plan_and_meaning_preservation_surgical_restore(tmp_path: Path) -> None:
    tokens = [
        # Beat 0 (0..9): setup with filler "یانی" at idx 3 and negation "نا" at idx 6
        "لە",
        "بۆشایی",
        "ئاسماندا",
        "یانی",
        "مرۆڤ",
        "هەرگیز",
        "نا",
        "ناتوانێت",
        "بێ",
        "ئۆکسجین",
        # Boring tangent (10..24) skipped completely by multi-cut!
        *(f"وشە{i}" for i in range(15)),
        # Beat 1 (25..39): payoff & concrete stat
        "بەڵام",
        "لە",
        "ساڵی",
        "1969",
        "ئەپۆلۆ",
        "گەیشتە",
        "سەر",
        "مانگ",
        "وەڵا",
        "ئەمە",
        "مێژووی",
        "مرۆڤایەتی",
        "بە",
        "تەواوی",
        "گۆڕی",
        # Extra words (40..64) so estimated duration comfortably clears minimum
        *(f"بەردەوام{i}" for i in range(25)),
    ]
    words = _make_words(tokens, step_ms=520, gap_ms=80)

    story_payload = {
        "stories": [
            {
                "story_id": "moon-vs-mars",
                "hook_title_ckb": "مرۆڤ چۆن گەیشتە سەر مانگ؟",
                "viral_score": 0.94,
                "rationale_ckb": "چیرۆکێکی تەواوی گەیشتن بە مانگ",
                "keep_spans": [
                    {"start_word_idx": 0, "end_word_idx": 9, "role": "hook"},
                    {"start_word_idx": 25, "end_word_idx": 64, "role": "payoff"},
                ],
                "drop_ranges": [
                    {"start_word_idx": 3, "end_word_idx": 3, "kind": "filler", "reason": "یانی"},
                    {
                        "start_word_idx": 6,
                        "end_word_idx": 6,
                        "kind": "redundant_clause",
                        "reason": "risky negation drop",
                    },
                    {"start_word_idx": 33, "end_word_idx": 33, "kind": "filler", "reason": "وەڵا"},
                ],
                "visual_cues": [
                    {
                        "anchor_word_idx": 28,
                        "duration_ms": 2800,
                        "layout": "stat_card",
                        "query_en": "apollo 11 moon landing 1969",
                        "stat_hero": "1969",
                        "label_ckb": "گەیشتن بە مانگ",
                    }
                ],
            }
        ]
    }
    gemini_story_resp = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(story_payload)}]}}]}
    )

    def _plan_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert "gemini-4-neon:generateContent" in url
        assert headers.get("x-goog-api-key") == "test-key"
        return 200, gemini_story_resp

    recipes = plan_episode_multicut_stories(
        words,
        backend="gemini",
        max_stories=2,
        min_duration_ms=20_000,
        max_duration_ms=60_000,
        api_key="test-key",
        transport=_plan_tx,
    )
    assert len(recipes) == 1
    rec = recipes[0]
    assert len(rec.keep_spans) == 2
    assert len(rec.drop_ranges) == 3

    long_words = _make_words(["وشە"] * 2250, step_ms=520, gap_ms=80)
    whole_episode = plan_episode_multicut_stories(
        long_words,
        backend="gemini",
        max_stories=3,
        min_duration_ms=15_000,
        max_duration_ms=55_000,
        api_key="test-key",
        transport=_plan_tx,
    )
    assert [story.keep_spans[0].start_word_idx for story in whole_episode] == [0, 1000, 2000]
    assert whole_episode[-1].visual_cues[0].anchor_word_idx == 2028
    assert whole_episode[-1].drop_ranges[0].start_word_idx == 2003

    requests = []

    def small_context(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert body is not None
        prompt = json.loads(body)["messages"][-1]["content"]
        requests.append(prompt)
        if "1200 total words" in prompt:
            return 400, '{"error": {"code": "context_length_exceeded"}}'
        return 200, json.dumps({"choices": [{"message": {"content": json.dumps(story_payload)}}]})

    resized = plan_episode_multicut_stories(
        long_words,
        backend="local-omni",
        model_id="local-test",
        max_stories=3,
        min_duration_ms=15_000,
        max_duration_ms=55_000,
        transport=small_context,
        checkpoint_dir=tmp_path / "nominations",
    )
    assert "1200 total words" in requests[0] and "600 total words" in requests[1]
    assert [story.keep_spans[0].start_word_idx for story in resized] == [0, 400, 800]
    assert "250 total words" in requests[-1]

    # After a restart, the oversized request times out; all smaller completed windows resume.
    def resumed(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert (
            body is not None and "1200 total words" in json.loads(body)["messages"][-1]["content"]
        )
        return 0, "timed out"

    assert (
        plan_episode_multicut_stories(
            long_words,
            backend="local-omni",
            model_id="local-test",
            max_stories=3,
            min_duration_ms=15_000,
            max_duration_ms=55_000,
            transport=resumed,
            checkpoint_dir=tmp_path / "nominations",
        )
        == resized
    )

    # Gemini 4 Carbon verifier catches drop[1] (the risky negation drop) and restores ONLY drop[1].
    verify_payload = {
        "approved": False,
        "restore_drop_indices": [1],
        "reason_ckb": "لابردنی نەرێنی ماناکە دەگۆڕێت",
    }
    gemini_verify_resp = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(verify_payload)}]}}]}
    )

    def _verify_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert "gemini-4-carbon:generateContent" in url
        return 200, gemini_verify_resp

    hardened, vres = verify_story_meaning_preservation(
        words, rec, backend="gemini", api_key="test-key", transport=_verify_tx
    )
    assert vres.approved is False
    assert vres.restored_drop_indices == (1,)
    assert len(hardened.drop_ranges) == 2
    assert all(dr.start_word_idx in (3, 33) for dr in hardened.drop_ranges)

    compiled = compile_story_to_assembly_spans(words, hardened)
    # 2 kept beats split around 2 approved single-word filler drops => 4 contiguous AssemblySpans!
    assert len(compiled.assembly_spans) == 4
    remapped_tokens = [w.w for w in compiled.remapped_words]
    assert "یانی" not in remapped_tokens
    assert "وەڵا" not in remapped_tokens
    assert "نا" in remapped_tokens  # restored by gemini-4-carbon!
    assert "وشە0" not in remapped_tokens  # skipped tangent!
    assert compiled.dropped_word_count == 2
    assert compiled.word_idx_to_output_ms[28] >= 0
    assert len(compiled.semantic_cut_times_ms) >= 1


def test_acoustic_rms_valley_snapping_and_crossfade_splice(tmp_path: Path) -> None:
    sr = 16_000
    # 1.0 s audio: loud consonant tone everywhere EXCEPT a quiet valley at 485..505 ms.
    samples: list[int] = []
    for i in range(sr):
        t_ms = (i * 1000) // sr
        if 485 <= t_ms <= 505:
            samples.append(20)
        else:
            samples.append(int(12_000 * math.sin(2.0 * math.pi * 440.0 * i / sr)))
    wav_path = _write_test_wav(tmp_path / "tone.wav", samples, sr=sr)
    assert wav_path.is_file()

    snapped = snap_cut_to_rms_valley(
        samples, sr, target_ms=520, min_ms=460, max_ms=550, search_radius_ms=40
    )
    assert 485 <= snapped <= 505

    w1 = Word(w="یەکەم", start_ms=100, end_ms=450, conf=1.0)
    w2 = Word(w="دووەم", start_ms=900, end_ms=1300, conf=1.0)
    spans = (
        AssemblySpan(0, 80, 480, 400, (Sentence(words=(w1,), complete=True),)),
        AssemblySpan(1, 880, 1320, 440, (Sentence(words=(w2,), complete=True),)),
    )
    filt = assembled_splice_filter(spans, crossfade_ms=24)
    assert "curve=qsin" in filt
    assert "afade=t=out" in filt
    assert "afade=t=in" in filt
    assert "concat=n=2:v=1:a=1[v_concat][a_concat]" in filt


def test_visual_aware_banter_split_and_cut_cover_choreography() -> None:
    # Wide 2-shot (0..6000 ms) with two tracks BOTH speaking within 1.5 s -> dual_active_banter!
    detections = [
        FaceDetectionFrame(at_ms=t, track_id=1, cx=160.0, cy=140.0, w=50.0, h=55.0)
        for t in range(0, 6000, 200)
    ] + [
        FaceDetectionFrame(at_ms=t, track_id=2, cx=480.0, cy=145.0, w=50.0, h=55.0)
        for t in range(0, 6000, 200)
    ]
    scores = [
        ActiveSpeakerScore(
            at_ms=t, track_id=1, score=0.45, is_speaking=True, backend="light_asd_onnx"
        )
        for t in range(400, 2400, 200)
    ] + [
        ActiveSpeakerScore(
            at_ms=t, track_id=2, score=0.52, is_speaking=True, backend="light_asd_onnx"
        )
        for t in range(1200, 3600, 200)
    ]
    crops = (
        LockedShotCrop(
            start_ms=0,
            end_ms=6000,
            focus_x_px=1440,
            face_center_y_px=420,
            face_height_px=165,
            active_track_id=2,
        ),
    )
    profiles = analyze_shot_visual_profiles(
        detections,
        scores,
        crops,
        source_width=1920,
        source_height=1080,
        proxy_width=640,
        proxy_height=360,
    )
    assert len(profiles) == 1
    assert profiles[0].shot_scale == "wide_2shot"
    assert profiles[0].dual_active_banter is True
    assert profiles[0].split_crops is not None
    top_c, bot_c = profiles[0].split_crops
    assert top_c[0] + top_c[2] <= 1920 and top_c[1] + top_c[3] <= 1080
    assert bot_c[0] + bot_c[2] <= 1920 and bot_c[1] + bot_c[3] <= 1080

    # Direct split crop helper bounds check
    tc, bc = compute_two_person_split_crops(400, 300, 180, 1500, 320, 180, 1920, 1080)
    assert tc[2] > 0 and bc[2] > 0

    # Cut cover choreography: near B-roll cue picks B-roll; distant cut picks split/punch
    cues = (
        VisualCue(
            anchor_word_idx=5,
            duration_ms=2600,
            layout="broll_fullscreen",
            query_en="mars planet surface",
        ),
    )
    actions = choreograph_cut_covers(
        semantic_cut_times_ms=((2_200, 800), (4_800, 900)),
        shot_profiles=profiles,
        visual_cues=cues,
        word_idx_to_output_ms={5: 2_300},
        duration_ms=10_000,
    )
    assert len(actions) == 2
    assert actions[0].kind == "broll_fullscreen"
    assert actions[0].start_ms <= 2_200 <= actions[0].end_ms
    assert actions[1].kind == "split_screen"


def test_broll_semantic_gate_provenance_and_filtergraph(tmp_path: Path) -> None:
    broll_dir = tmp_path / "studio_broll"
    broll_dir.mkdir()
    img = broll_dir / "mars_red_planet.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 128)
    vid = broll_dir / "rocket_launch_space.mp4"
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 128)

    # NonCommercial license MUST be rejected
    with pytest.raises(BRollError, match="NonCommercial"):
        write_asset_provenance(img, provider="test", license_name="CC BY-NC 4.0", query_en="mars")

    # Commercial-safe license passes render.assert_asset_provenance
    write_asset_provenance(img, provider="local", license_name="CC0 1.0", query_en="mars")
    assert_asset_provenance(img)

    # Cosine similarity gate: < 0.26 rejected, >= 0.26 accepted
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    call_idx = {"n": 0}

    def _low_sim_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, bytes]:
        call_idx["n"] += 1
        vec = [1.0, 0.0, 0.0] if call_idx["n"] % 2 == 1 else [0.1, 0.99, 0.0]
        return 200, json.dumps({"embedding": {"values": vec}}).encode("utf-8")

    ok_low, sim_low = verify_broll_relevance(
        img, "mars planet", api_key="k", min_similarity=0.26, transport=_low_sim_tx
    )
    assert ok_low is False and sim_low < 0.26

    def _high_sim_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, bytes]:
        return 200, json.dumps({"embedding": {"values": [0.8, 0.6, 0.0]}}).encode("utf-8")

    ok_hi, sim_hi = verify_broll_relevance(
        img, "mars planet", api_key="k", min_similarity=0.26, transport=_high_sim_tx
    )
    assert ok_hi is True and sim_hi >= 0.99

    # Resolve visual cues -> BRollItem (provenance-signed) + Stat Card fallback
    cues = (
        VisualCue(
            anchor_word_idx=2,
            duration_ms=2600,
            layout="broll_fullscreen",
            query_en="mars red planet",
        ),
        VisualCue(
            anchor_word_idx=8,
            duration_ms=2800,
            layout="stat_card",
            query_en="fifty years space",
            stat_hero="50 ساڵ",
            label_ckb="دوای گەیشتن بە مانگ",
        ),
    )
    b_items, stat_vis = resolve_visual_cues_to_broll(
        cues,
        {2: 4_000, 8: 12_000},
        duration_ms=30_000,
        cache_dir=tmp_path / "cache",
        broll_dir=broll_dir,
        enable_web_stock=False,
        enable_ai_images=False,
        verify_with_gemini=True,
        api_key="k",
        transport=_high_sim_tx,
    )
    assert len(b_items) == 1
    assert b_items[0].position == "fullscreen"
    assert b_items[0].ken_burns is True
    assert len(stat_vis) == 1
    assert stat_vis[0].text_ckb == "50 ساڵ | دوای گەیشتن بە مانگ"

    # FFmpeg filtergraph synthesis: fullscreen Ken Burns still + caption scrim + rounded top_pip
    fs_clause, next_tag = build_broll_overlay_clause(1, b_items[0], 0, "[v_cut]", fps=25.0)
    assert "zoompan=" in fs_clause
    assert "drawbox=x=0:y=1240:w=1080:h=380:color=black@0.38:t=fill" in fs_clause
    assert "overlay=x=0:y=0" in fs_clause
    assert next_tag == "[v_brolled_0]"

    pip_item = BRollItem(path=vid, start_ms=8000, duration_ms=2500, position="top_pip", width=860)
    pip_clause, _ = build_broll_overlay_clause(2, pip_item, 1, next_tag, fps=25.0)
    assert "trim=duration=2.500" in pip_clause
    assert "pad=iw+6:ih+6:3:3:color=0xFFD700@0.92" in pip_clause
    assert "geq=r='r(X,Y)'" in pip_clause
    assert "loop=loop=-1" not in pip_clause


def test_v10_3_timelens2_gesture_protection_and_cc0_music_bed(tmp_path: Path) -> None:
    from hawedit.sound_design import write_cinema_sfx_wav

    groundings = VisualGroundings(
        sv6d_lines=("subject | 2.0 | speaker gestures emphatically",),
        gesture_intervals_ms=((2_000, 4_500, "speaker gesture"),),
        models_used=("MCG-NJU/TimeLens2-4B", "MCG-NJU/VideoChat3-4B"),
    )
    closeup = ShotVisualProfile(
        start_ms=0,
        end_ms=6_000,
        shot_scale="closeup",
        track_ids=(1,),
        dual_active_banter=False,
        hand_motion_energy=0.05,
        safe_overlay_zone="chest",
    )
    upgraded = apply_visual_groundings_to_profiles((closeup,), groundings)
    assert upgraded[0].safe_overlay_zone == "top_pip"

    fs_act = CutCoverAction(
        at_ms=3_000,
        start_ms=2_500,
        end_ms=5_000,
        kind="broll_fullscreen",
        reason="cover cut",
        cue_index=0,
    )
    protected = protect_visual_gestures_in_cuts((fs_act,), groundings)
    assert protected[0].kind == "broll_pip"
    assert "TimeLens2" in protected[0].reason

    # CC0 procedural ambient music bed ducks measurably under active speech intervals
    bed_wav = write_cinema_sfx_wav(
        tmp_path / "bed.wav",
        duration_ms=4_000,
        transition_ms=(2_000,),
        pop_ms=(1_500,),
        include_hook_thump=False,
        music_mood="curious",
        speech_intervals_ms=((2_200, 3_600),),
    )
    assert bed_wav.is_file() and bed_wav.stat().st_size > 100_000
    with wave.open(str(bed_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = struct.unpack(f"<{len(raw) // 2}h", raw)
    # Idle music energy (800..1300 ms) should be louder than speech-ducked energy (2600..3200 ms).
    sr = 48_000
    idle_rms = math.sqrt(sum(s * s for s in pcm[int(0.8 * sr) : int(1.3 * sr)]) / (0.5 * sr))
    duck_rms = math.sqrt(sum(s * s for s in pcm[int(2.6 * sr) : int(3.2 * sr)]) / (0.6 * sr))
    assert idle_rms > duck_rms * 1.4


def test_v10_3_episode_overgenerate_quarantines_bad_candidate_and_promotes_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.v8 import episode as ep_mod
    from hawedit.v8.compiler import (
        SubtitleArtifact,
        V8CompileError,
        V8CompileResult,
        VideoGrillReport,
    )
    from hawedit.v8.schema import DirectorScript
    from hawedit.v8.story_editor import (
        MeaningVerificationResult,
        MultiCutStoryRecipe,
        WordSpan,
    )

    src_mp4 = tmp_path / "ep.mp4"
    src_mp4.write_bytes(b"\x00" * 64)
    words = _make_words([f"وشە{i}" for i in range(60)], step_ms=400, gap_ms=50)
    transcript_json = tmp_path / "ep.transcript.json"
    transcript_json.write_text(
        json.dumps(
            {
                "words": [
                    {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                    for w in words
                ]
            }
        ),
        encoding="utf-8",
    )

    recipes = (
        MultiCutStoryRecipe(
            story_id="bad-cand",
            hook_title_ckb="چیرۆکی خراپ",
            keep_spans=(WordSpan(0, 24, "hook"),),
            drop_ranges=(),
            visual_cues=(),
            rationale_ckb="cand 1",
            viral_score=0.95,
        ),
        MultiCutStoryRecipe(
            story_id="good-cand",
            hook_title_ckb="چیرۆکی سەرکەوتوو",
            keep_spans=(WordSpan(30, 59, "hook"),),
            drop_ranges=(),
            visual_cues=(),
            rationale_ckb="cand 2",
            viral_score=0.90,
        ),
    )

    monkeypatch.setattr(ep_mod, "plan_episode_multicut_stories", lambda *a, **kw: recipes)
    monkeypatch.setattr(ep_mod, "refine_story_pruning", lambda w, r, **kw: r)
    monkeypatch.setattr(
        ep_mod,
        "verify_story_meaning_preservation",
        lambda w, r, **kw: (
            r,
            MeaningVerificationResult(True, (), "ok", "gemini-4-carbon"),
        ),
    )
    monkeypatch.setattr(ep_mod, "find_ffmpeg", lambda: None)

    calls = {"n": 0}

    def _fake_compiler(**kwargs: Any) -> V8CompileResult:
        calls["n"] += 1
        out_dir = Path(kwargs["out_dir"])
        cid = str(kwargs["clip_id"])
        mp4 = out_dir / f"{cid}.v8.mp4"
        mp4.write_bytes(b"mp4-bytes")
        if calls["n"] == 1:
            raise V8CompileError("Simulated forensic grill defect on candidate 1")
        ass = out_dir / f"{cid}.v8.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        sc_path = out_dir / f"{cid}.director.json"
        script = DirectorScript(
            clip_id=cid,
            hook_title_ckb=str(kwargs.get("semantic_hook_title_ckb") or "چیرۆک"),
            word_repairs=(),
            cuts=(),
            camera_moves=(),
            caption_beats=(),
            visual_interrupts=(),
        )
        sc_path.write_text(script.to_json(), encoding="utf-8")
        intervals = tuple(
            (sp.source_in_ms, sp.source_out_ms) for sp in kwargs["semantic_assembly_spans"]
        )
        duration = sum(end - start for start, end in intervals)
        grill = VideoGrillReport(
            mp4_path=mp4,
            duration_ms=duration,
            fps=25.0,
            frame_count=round(duration / 40),
            cut_times_s=(),
            double_cuts=(),
            trailing_cuts=(),
            long_silences=(),
            audio_flat_factor=0.0,
            passed=True,
            defects=(),
        )
        (out_dir / f"{cid}.grill.json").write_text(json.dumps(grill.to_dict()), encoding="utf-8")
        return V8CompileResult(
            clip_id=cid,
            output_mp4=mp4,
            script=script,
            script_path=sc_path,
            repaired_words=tuple(kwargs["semantic_words"]),
            camera_filter="",
            camera_jump_cuts_ms=(),
            subtitles=SubtitleArtifact(engine="libass", ass_path=ass, chunk_count=4),
            locked_crops=(),
            critique=None,
            critique_revisions=0,
            director_backend="gemini",
            sub_engine="libass",
            grill_report=grill,
            retained_intervals_ms=intervals,
        )

    def _fake_cover(mp4: Path, out_png: Path, ts: float) -> Path:
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        return out_png

    res = ep_mod.compile_v8_episode(
        source=src_mp4,
        out_dir=tmp_path / "out",
        transcript_path=transcript_json,
        config=ep_mod.V8EpisodeConfig(
            director="gemini",
            max_clips=1,
            overgenerate_candidates=True,
            story_mode="semantic-multicut",
        ),
        clip_compiler=_fake_compiler,
        cover_extractor=_fake_cover,
    )
    assert len(res.clips) == 1
    assert res.clips[0].hook_title_ckb == "چیرۆکی سەرکەوتوو"
    assert len(res.quarantined) == 1
    assert res.quarantined[0]["story_id"] == "bad-cand"
    assert (tmp_path / "out/quarantine/cand-01-bad-cand.v8.mp4").read_bytes() == b"mp4-bytes"
    assert (tmp_path / "out" / "quarantine" / "cand-01-bad-cand.quarantine.json").is_file()


def test_v11_two_pass_cold_open_stumble_refiner_and_acoustic_tags(tmp_path: Path) -> None:
    from hawedit.v8.story_editor import (
        _format_indexed_episode_transcript,
        refine_story_pruning,
    )

    tokens = [
        # Setup with spoken stumble "پۆست پۆدکاستە" (idx 1..2)
        "ئەم",
        "پۆست",
        "پۆدکاستە",
        "باس",
        "لە",
        "نهێنی",
        "گەردوون",
        "دەکات",
        # Pause then high-energy climax words (indices 8..13) used as cold-open teaser
        "مرۆڤ",
        "پەنجا",
        "ساڵە",
        "نەگەڕاوەتەوە",
        "سەر",
        "مانگ",
        # Extra payoff words so duration comfortably passes bounds
        *(f"وردەکاری{i}" for i in range(42)),
    ]
    words: list[Word] = []
    t = 1_000
    for idx, tok in enumerate(tokens):
        if idx == 8:
            t += 1_200  # 1.2 s pause before climax
        words.append(Word(w=tok, start_ms=t, end_ms=t + 480, conf=0.95))
        t += 520

    # Write 16 kHz mono WAV with loud energy on climax (words 8..13) and quiet speech elsewhere.
    sr = 16_000
    total_s = (words[-1].end_ms // 1000) + 2
    samples = [250] * (sr * total_s)
    hi_s = int((words[8].start_ms * sr) // 1000)
    hi_e = int((words[13].end_ms * sr) // 1000)
    for i in range(hi_s, min(len(samples), hi_e)):
        samples[i] = int(14_000 * math.sin(2.0 * math.pi * 320.0 * i / sr))
    wav_path = _write_test_wav(tmp_path / "ep.wav", samples, sr=sr)

    formatted = _format_indexed_episode_transcript(words, audio_wav=wav_path)
    assert "[PAUSE:1.2s]" in formatted
    assert "[ENERGY:HIGH]" in formatted

    plan_payload = {
        "stories": [
            {
                "story_id": "cold-open-moon",
                "hook_title_ckb": "بۆچی نەگەڕاینەوە سەر مانگ؟",
                "viral_score": 0.96,
                "rationale_ckb": "تیزەری بەهێز",
                "cold_open_span": {"start_word_idx": 8, "end_word_idx": 13},
                "keep_spans": [
                    {"start_word_idx": 0, "end_word_idx": 55, "role": "hook"},
                ],
                "drop_ranges": [],
                "visual_cues": [],
            }
        ]
    }
    plan_resp = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(plan_payload)}]}}]}
    )
    recipes = plan_episode_multicut_stories(
        words,
        backend="gemini",
        max_stories=1,
        min_duration_ms=20_000,
        max_duration_ms=60_000,
        audio_wav=wav_path,
        api_key="k",
        transport=lambda u, b, h: (200, plan_resp),
    )
    assert len(recipes) == 1
    assert recipes[0].cold_open_span is not None
    assert recipes[0].cold_open_span.role == "cold_open"

    # Pass 2 refiner catches spoken stumble idx=1 ("پۆست" before "پۆدکاستە") + adds stat cue.
    refine_payload = {
        "hook_title_ckb": "نهێنی ٥٠ ساڵەی سەر مانگ",
        "drop_ranges": [
            {
                "start_word_idx": 1,
                "end_word_idx": 1,
                "kind": "stumble",
                "reason": "spoken false start before پۆدکاستە",
            }
        ],
        "visual_cues": [
            {
                "anchor_word_idx": 9,
                "duration_ms": 2800,
                "layout": "stat_card",
                "query_en": "50 years moon landing",
                "stat_hero": "50 ساڵ",
                "label_ckb": "بێ گەڕانەوە بۆ مانگ",
            }
        ],
    }
    refine_resp = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": json.dumps(refine_payload)}]}}]}
    )
    refined = refine_story_pruning(
        words,
        recipes[0],
        backend="gemini",
        api_key="k",
        transport=lambda u, b, h: (200, refine_resp),
    )
    assert refined.hook_title_ckb == "نهێنی ٥٠ ساڵەی سەر مانگ"
    assert len(refined.drop_ranges) == 1
    assert refined.drop_ranges[0].kind == "stumble"
    assert len(refined.visual_cues) == 1

    compiled = compile_story_to_assembly_spans(words, refined)
    assert compiled.assembly_spans[0].role == "cold_open"
    assert compiled.cold_open_end_ms is not None and compiled.cold_open_end_ms >= 2_500
    assert compiled.remapped_words[0].w == "مرۆڤ"
    assert "پۆست" not in [w.w for w in compiled.remapped_words]
    assert "پۆدکاستە" in [w.w for w in compiled.remapped_words]


def test_v11_dual_query_timelens2_reaction_split_director_context_and_riser(
    tmp_path: Path,
) -> None:
    from hawedit.sound_design import write_cinema_sfx_wav
    from hawedit.v8.director import GeminiVideoDirector
    from hawedit.v8.visual_aware import format_visual_groundings_for_director

    groundings = VisualGroundings(
        sv6d_lines=("subject | 3.0 | host and guest laughing in studio",),
        gesture_intervals_ms=((1_000, 2_200, "hand gesture"),),
        reaction_intervals_ms=((3_000, 5_000, "laughing broadly"),),
        models_used=("MCG-NJU/TimeLens2-4B", "MCG-NJU/VideoChat3-4B"),
    )
    wide = ShotVisualProfile(
        start_ms=0,
        end_ms=6_000,
        shot_scale="wide_2shot",
        track_ids=(1, 2),
        dual_active_banter=False,
        hand_motion_energy=0.04,
        safe_overlay_zone="top",
        split_crops=((0, 0, 960, 854), (960, 0, 960, 854)),
    )
    upgraded = apply_visual_groundings_to_profiles((wide,), groundings)
    assert upgraded[0].dual_active_banter is True

    # TimeLens2 reaction interval also downgrades overlapping fullscreen B-roll to top_pip.
    act = CutCoverAction(
        at_ms=3_500,
        start_ms=3_100,
        end_ms=5_200,
        kind="broll_fullscreen",
        reason="cut cover",
        cue_index=0,
    )
    protected = protect_visual_gestures_in_cuts((act,), groundings)
    assert protected[0].kind == "broll_pip"

    ctx_lines = format_visual_groundings_for_director(groundings, upgraded)
    assert any("VideoChat3 SV6D" in ln for ln in ctx_lines)
    assert any("TimeLens2 reaction" in ln for ln in ctx_lines)
    assert any("50/50 split-screen active" in ln for ln in ctx_lines)

    # Verify GeminiVideoDirector forwards visual_context cleanly into generateContent prompt.
    captured_prompt: dict[str, str] = {}
    dummy_proxy = tmp_path / "proxy.mp4"
    dummy_proxy.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    words = _make_words(["سڵاو", "هاوڕێیان", "ئەمڕۆ", "نهێنی", "گەردوون"], step_ms=400, gap_ms=50)
    script_json = {
        "clip_id": "c1",
        "hook_title_ckb": "نهێنی گەردوون چییە؟",
        "word_repairs": [],
        "cuts": [],
        "camera_moves": [],
        "caption_beats": [{"word_indices": [0, 1], "power_word_index": None, "accent_color": None}],
        "visual_interrupts": [],
        "cold_open_span_ms": None,
    }

    def _cap_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert body is not None
        req = json.loads(body.decode("utf-8"))
        captured_prompt["text"] = req["contents"][0]["parts"][1]["text"]
        return 200, json.dumps(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(script_json)}]}}]}
        )

    director = GeminiVideoDirector(api_key="k", transport=_cap_tx)
    director.direct_clip(
        source_mp4=dummy_proxy,
        clip_in_ms=0,
        clip_out_ms=6_000,
        clip_id="c1",
        words=words,
        video_proxy=dummy_proxy,
        visual_context=ctx_lines,
    )
    assert "VideoChat3-4B / TimeLens2-4B" in captured_prompt["text"]
    assert "laughing broadly" in captured_prompt["text"]

    # Verify cold-open riser synthesis produces measurable rising energy right before riser_ms.
    riser_wav = write_cinema_sfx_wav(
        tmp_path / "riser.wav",
        duration_ms=5_000,
        riser_ms=(3_000,),
        include_hook_thump=False,
        music_mood="none",
    )
    with wave.open(str(riser_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = struct.unpack(f"<{len(raw) // 2}h", raw)
    sr = 48_000
    quiet_rms = math.sqrt(sum(s * s for s in pcm[int(1.0 * sr) : int(1.5 * sr)]) / (0.5 * sr))
    riser_rms = math.sqrt(sum(s * s for s in pcm[int(2.7 * sr) : int(3.0 * sr)]) / (0.3 * sr))
    assert quiet_rms < 1.0
    assert riser_rms > 80.0

    # Verify LM Studio's exact input_audio schema rejection steps down cleanly from omni -> vision.
    from hawedit.v8.director import _is_input_audio_rejection

    lm_err = (
        "{\"error\":\"Invalid 'content': 'content' objects must have a 'type' field that is "
        "either 'text' or 'image_url'.\"}"
    )
    assert _is_input_audio_rejection(400, lm_err) is True


def test_v11_1_stumble_dedup_emphatic_preserve_dangling_end_and_split_seam_captions() -> None:
    from hawedit.v8.story_editor import MultiCutStoryRecipe, WordSpan
    from hawedit.v8.tiktok_subs import (
        ViralCaptionChunk,
        ViralCaptionWord,
        render_tiktok_frame_rgba,
    )

    # 1. Adjacent non-emphatic stumble ('ئەوە ئەوە') & 'بەخوا' pruned; emphatic 'زۆر زۆر' kept;
    #    dangling ending ('و ئەمانەیان') trimmed cleanly off the final beat.
    tokens = [
        "زانست",
        "زۆر",
        "زۆر",
        "گرینگە",
        "ئەوە",
        "ئەوە",
        "کێشەیە",
        "نازانم",
        "بەخوا",
        "لە",
        "خوێندنی",
        "حکوومی",
        "و",
        "ئەمانەیان",
    ]
    words = _make_words(tokens, step_ms=300, gap_ms=60)
    rec = MultiCutStoryRecipe(
        story_id="clean-end",
        hook_title_ckb="بۆچی زانست گرینگە؟",
        keep_spans=(WordSpan(0, len(words) - 1, "hook"),),
        drop_ranges=(),
        visual_cues=(),
        rationale_ckb="test",
        viral_score=0.9,
    )
    compiled = compile_story_to_assembly_spans(words, rec)
    out_toks = [w.w for w in compiled.remapped_words]
    assert out_toks.count("زۆر") == 2  # emphatic reduplication preserved!
    assert out_toks.count("ئەوە") == 1  # immediate stumble deduped!
    assert "بەخوا" not in out_toks
    assert "نازانم" not in out_toks
    assert out_toks[-1] == "حکوومی"  # dangling 'و ئەمانەیان' trimmed!

    # 2. Split-screen window shifts caption rendering from y=1380 up to exact center seam y=960.
    font_path = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Vazirmatn.ttf"
    chunk = ViralCaptionChunk(
        words=(ViralCaptionWord(0, "زانست", 1_000, 1_800, is_power_word=False),),
        start_ms=1_000,
        end_ms=1_800,
    )
    normal_rgba = render_tiktok_frame_rgba(
        (chunk,), t_ms=1_300, font_path=font_path, y_center_px=1380
    )
    split_rgba = render_tiktok_frame_rgba(
        (chunk,),
        t_ms=1_300,
        font_path=font_path,
        y_center_px=1380,
        split_screen_windows_ms=((500, 2_500),),
    )
    row_b = 1080 * 4
    # At y=960 center seam, split_rgba has opaque caption pixels while normal_rgba is transparent.
    seam_alpha_normal = sum(normal_rgba[960 * row_b + 3 : 961 * row_b : 4])
    seam_alpha_split = sum(split_rgba[960 * row_b + 3 : 961 * row_b : 4])
    low_alpha_split = sum(split_rgba[1380 * row_b + 3 : 1381 * row_b : 4])
    assert seam_alpha_normal == 0
    assert seam_alpha_split > 10_000
    assert low_alpha_split == 0
    # Chunk straddling a split-screen start (>=1/3 overlap) also snaps to seam.
    straddle_chunk = ViralCaptionChunk(
        words=(ViralCaptionWord(0, "بەڵێ", 500, 830, is_power_word=False),),
        start_ms=500,
        end_ms=830,
    )
    straddle_rgba = render_tiktok_frame_rgba(
        (straddle_chunk,),
        t_ms=780,
        font_path=font_path,
        y_center_px=1380,
        split_screen_windows_ms=((680, 6_680),),
    )
    assert sum(straddle_rgba[960 * row_b + 3 : 961 * row_b : 4]) > 10_000
    assert sum(straddle_rgba[1380 * row_b + 3 : 1381 * row_b : 4]) == 0


def test_v11_2_local_vision_broll_gate_and_kurdish_stat_extraction(tmp_path: Path) -> None:
    from hawedit.v8.broll import (
        extract_kurdish_stat_interrupts,
        verify_broll_relevance_local,
    )

    img = tmp_path / "space_telescope.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 128)

    # 1. Local vision gate rejects book covers/text clutter even if score is high.
    def _clutter_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, bytes]:
        verdict = {
            "relevant": True,
            "score": 0.88,
            "has_text_clutter": True,
            "reason": "Book cover with prominent English title text",
        }
        resp = {"choices": [{"message": {"content": json.dumps(verdict)}}]}
        return 200, json.dumps(resp).encode("utf-8")

    ok_clutter, sc_clutter = verify_broll_relevance_local(
        img,
        "deep space nebula stars",
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        transport=_clutter_tx,
    )
    assert ok_clutter is False and sc_clutter == pytest.approx(0.88)

    # 2. Clean high-relevance photograph passes local vision gate.
    def _clean_tx(url: str, body: bytes | None, headers: Any) -> tuple[int, bytes]:
        assert body is not None and b"image_url" in body
        verdict = {
            "relevant": True,
            "score": 0.91,
            "has_text_clutter": False,
            "reason": "Clean cinematic night sky nebula photo",
        }
        resp = {"choices": [{"message": {"content": json.dumps(verdict)}}]}
        return 200, json.dumps(resp).encode("utf-8")

    ok_clean, sc_clean = verify_broll_relevance_local(
        img,
        "deep space nebula stars",
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        transport=_clean_tx,
    )
    assert ok_clean is True and sc_clean == pytest.approx(0.91)

    # 3. Deterministic Sorani numeric Stat Card extraction ('سەتا 15 بۆ 20' & 'سەتا هەشتای').
    words = [
        Word("کۆمەڵگەی", 500, 900, 1.0),
        Word("کوردی", 950, 1_300, 1.0),
        Word("ڕەنگە", 4_500, 4_900, 1.0),
        Word("سەتا", 5_000, 5_300, 1.0),
        Word("15", 5_350, 5_650, 1.0),
        Word("بۆ", 5_700, 5_900, 1.0),
        Word("20", 5_950, 6_250, 1.0),
        Word("نوخبەی", 6_300, 6_700, 1.0),
        Word("زانستی", 6_750, 7_200, 1.0),
        Word("کۆمەڵگا", 7_250, 7_800, 1.0),
        Word("ئەوەی", 16_000, 16_400, 1.0),
        Word("تر", 16_450, 16_700, 1.0),
        Word("سەتا", 16_800, 17_100, 1.0),
        Word("هەشتای", 17_150, 17_600, 1.0),
        Word("ئاستی", 17_650, 18_000, 1.0),
        Word("لاوازی", 18_050, 18_500, 1.0),
        Word("زانستی", 18_550, 19_000, 1.0),
    ]
    cards = extract_kurdish_stat_interrupts(words, duration_ms=26_000)
    assert len(cards) == 2
    assert cards[0].text_ckb.startswith("15–20% | ")
    assert "نوخبەی زانستی" in cards[0].text_ckb
    assert cards[1].text_ckb.startswith("80% | ")
    assert "ئاستی لاوازی" in cards[1].text_ckb


def test_local_ranker_can_only_select_measured_source_excerpts() -> None:
    from hawedit.v8.story_editor import StoryEditorError, rank_local_source_spans

    words = _make_words(["word"] * 240, step_ms=500, gap_ms=50)
    spans = [(0, 39), (50, 89), (100, 139), (150, 189)]
    scores = [35, 87, 79, 99]

    def score(url: str, body: bytes | None, headers: Any) -> tuple[int, str]:
        assert body is not None
        request = json.loads(body)
        excerpts = json.loads(request["messages"][1]["content"])
        assert len(excerpts) <= 3
        response = {
            k: {"score": scores[int(k[4:]) - 1], "hook": "headline", "reason": "reason"}
            for k in excerpts
        }
        return 200, json.dumps({"choices": [{"message": {"content": json.dumps(response)}}]})

    results = rank_local_source_spans(words, spans, max_stories=2, model_id="test", transport=score)
    assert [r.story_id for r in results] == ["shortlist-150-189", "shortlist-50-89"]
    assert results[0].keep_spans[0].end_word_idx == 189
    with pytest.raises(StoryEditorError, match="every source candidate"):
        rank_local_source_spans(
            words,
            spans,
            max_stories=2,
            model_id="test",
            transport=lambda *_: (200, '{"choices":[{"message":{"content":"{}"}}]}'),
        )
