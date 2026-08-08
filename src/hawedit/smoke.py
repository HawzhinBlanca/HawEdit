"""A live check against the real Gemini API — opt-in, cheap, and honest about cost.

    python -m hawedit.smoke --video sample.mp4

Everything Gemini in this project is tested offline through an injected transport, which is
right: a suite that needed a live key would push people toward committing one. But offline
tests cannot answer the question that matters on the day a key arrives — *does this actually
work against Google, with my key, on my quota?* A mocked transport agrees with whatever the
mock was written to believe.

So this is the one place that spends money, and it announces what it will spend before it does.
It runs the two model stages the pipeline makes — §3 Stage 3 Path A over a transcript, then §3
Stage 4 on the top candidate with actual keyframes from a matching sample video — and prints
what came back, including the Kurdish title. Roughly a thousand tokens; a fraction of a cent.

What it is checking is not "did the HTTP request succeed". It is the set of things that only
break against a real model: whether `gemini-2.5-pro` is enabled on this key's project, whether
the structured-output schema survives a real response, whether the model actually answers in
Kurdish when asked to, and whether the spans it returns land inside the transcript.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hawedit.credentials import GEMINI_API_KEY, mask, read_credential
from hawedit.gemini import GeminiJudge, GeminiUnavailable, JudgeUnusable
from hawedit.judge import InputMode, JudgeRequest, estimate_cost_usd
from hawedit.keyframes import KeyframeError, extract_judge_frames
from hawedit.path_a import PathADiscovery
from hawedit.transcripts import AsrProvenance, RawTranscript, Word, normalize_transcript

__all__ = ["SAMPLE", "main"]

# A short Sorani sample with real word timings. Deliberately not the caption fixture: this is
# about the model reading Kurdish, so the text is ordinary journalistic prose rather than a
# string chosen to exercise shaping.
SAMPLE = RawTranscript(
    media_id="smoke",
    text_ckb=(
        "ڕۆژنامەوانی کوردی لە هەولێر گەشەیەکی زۆری کردووە. "
        "زۆرێک لە گەنجان ئێستا کاری ڕۆژنامەوانی دەکەن. "
        "بەڵام هێشتا کێشەی دارایی هەیە بۆ زۆربەی دەزگاکان."
    ),
    words=(
        Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=900, conf=0.95),
        Word(w="کوردی", start_ms=900, end_ms=1_400, conf=0.94),
        Word(w="لە", start_ms=1_400, end_ms=1_600, conf=0.93),
        Word(w="هەولێر", start_ms=1_600, end_ms=2_300, conf=0.95),
        Word(w="گەشەیەکی", start_ms=2_300, end_ms=3_000, conf=0.92),
        Word(w="زۆری", start_ms=3_000, end_ms=3_400, conf=0.93),
        Word(w="کردووە.", start_ms=3_400, end_ms=4_200, conf=0.94),
        Word(w="زۆرێک", start_ms=4_600, end_ms=5_100, conf=0.93),
        Word(w="لە", start_ms=5_100, end_ms=5_300, conf=0.92),
        Word(w="گەنجان", start_ms=5_300, end_ms=5_900, conf=0.94),
        Word(w="ئێستا", start_ms=5_900, end_ms=6_400, conf=0.93),
        Word(w="کاری", start_ms=6_400, end_ms=6_800, conf=0.92),
        Word(w="ڕۆژنامەوانی", start_ms=6_800, end_ms=7_700, conf=0.95),
        Word(w="دەکەن.", start_ms=7_700, end_ms=8_400, conf=0.94),
        Word(w="بەڵام", start_ms=8_900, end_ms=9_400, conf=0.93),
        Word(w="هێشتا", start_ms=9_400, end_ms=9_900, conf=0.92),
        Word(w="کێشەی", start_ms=9_900, end_ms=10_400, conf=0.93),
        Word(w="دارایی", start_ms=10_400, end_ms=11_000, conf=0.94),
        Word(w="هەیە", start_ms=11_000, end_ms=11_400, conf=0.93),
        Word(w="بۆ", start_ms=11_400, end_ms=11_600, conf=0.92),
        Word(w="زۆربەی", start_ms=11_600, end_ms=12_200, conf=0.93),
        Word(w="دەزگاکان.", start_ms=12_200, end_ms=13_000, conf=0.94),
    ),
    asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
)


def main(argv: list[str] | None = None) -> int:
    """Run the two real API calls the pipeline makes, and report what came back."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="hawedit.smoke",
        description="Live check against the real Gemini API. Spends a fraction of a cent.",
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt (for scripts)"
    )
    parser.add_argument(
        "--video",
        type=Path,
        help="video matching the built-in Sorani sample; required for pixel-grounded Stage 4",
    )
    args = parser.parse_args(argv)

    key = read_credential(GEMINI_API_KEY)
    if key is None:
        print(f"✗ no {GEMINI_API_KEY}. Run `python -m hawedit.credentials` first.", file=sys.stderr)
        return 2

    normalized = normalize_transcript(SAMPLE)
    print("hawedit live check — §3 Stage 3 Path A, then §3 Stage 4\n")
    print(f"key         {mask(key)}")
    print(f"transcript  {len(SAMPLE.words)} words, {SAMPLE.words[-1].end_ms / 1000:.1f} s")
    print(f"estimate    ~{estimate_cost_usd(1_500):.4f} USD for both calls\n")

    if not args.yes:
        try:
            if input(
                "This makes two real, billed API calls. Continue? [y/N] "
            ).strip().lower() not in {
                "y",
                "yes",
            }:
                print("nothing sent")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nnothing sent")
            return 0

    # --- §3 Stage 3 Path A ----------------------------------------------------------------
    try:
        path_a = PathADiscovery(api_key=key)
        request = path_a.build_request(normalized)
        tokens = path_a._judge.count_request_tokens(
            JudgeRequest(
                candidate_id=request.candidate_id,
                mode=request.mode,
                text_ckb=path_a._prompt(normalized),
                clip_in_ms=0,
                clip_out_ms=SAMPLE.words[-1].end_ms,
            )
        )
        print(f"\n==> Path A  ({tokens:,} tokens, ~{estimate_cost_usd(tokens):.4f} USD)")
        candidates = path_a.discover(normalized)
    except (GeminiUnavailable, JudgeUnusable) as exc:
        print(f"✗ Path A failed: {exc}", file=sys.stderr)
        return 1

    if not candidates:
        print("  the judge found no candidates in this sample.")
        print("\n  That is a valid answer, but it means Stage 4 has nothing to score.")
        return 1
    for candidate in candidates:
        print(
            f"  #{candidate.rank}  {candidate.in_ms:>6}..{candidate.out_ms:<6} ms  "
            f"score {candidate.score}"
        )

    # --- §3 Stage 4 -----------------------------------------------------------------------
    top = candidates[0]
    print("\n==> Stage 4")
    if args.video is None:
        print("✗ Stage 4 needs --video; text-only visual judging is refused", file=sys.stderr)
        return 1
    if not args.video.is_file():
        print(f"✗ no sample video at {args.video}", file=sys.stderr)
        return 2
    try:
        keyframes = extract_judge_frames(
            args.video,
            top.in_ms,
            top.out_ms,
            Path(".gate") / "gemini-smoke-keyframes",
        )
        verdict = GeminiJudge(api_key=key).judge(
            JudgeRequest(
                candidate_id=top.candidate_id,
                mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
                text_ckb=normalized.text_ckb,
                carried_verbal_score=top.score,
                clip_in_ms=top.in_ms,
                clip_out_ms=top.out_ms,
                keyframes=keyframes,
            )
        )
    except (GeminiUnavailable, JudgeUnusable, KeyframeError) as exc:
        print(f"✗ Stage 4 failed: {exc}", file=sys.stderr)
        return 1

    print(f"  hook            {verdict.hook_score}")
    print(f"  self-contained  {verdict.self_contained}")
    print(f"  payoff at       {verdict.payoff_at_ms} ms")
    print(f"  meaning         {verdict.meaning_fidelity}")
    print(f"  misleading risk {verdict.misleading_edit_risk}")
    print(f"  cultural        {verdict.cultural_landing}")
    print(f"  title           {verdict.title_ckb}")
    print(f"  hashtags        {' '.join(verdict.hashtags_ckb) or '(none)'}")

    print(
        "\n✓ live path works: the key is valid, gemini-2.5-pro is enabled on it, the schema "
        "survived a real response, and the model answered in Kurdish."
    )
    print(
        "  Still required before a client job: the §3 zero-data-retention answer for "
        "confidential material (BLOCKED.md #3)."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
