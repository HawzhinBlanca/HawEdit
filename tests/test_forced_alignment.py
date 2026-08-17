"""M1.1 — §4.2 Viterbi forced alignment against CTC emissions.

§4.2: "Implement Viterbi forced alignment against OmniASR CTC-3B emissions. You already run
the acoustic model, so there is no second model and no alignment mismatch. This is a real
engineering module with its own tests, not a library call — Meta does not ship timestamp
extraction as a finished feature."

It is also the module §7 attributes to us: "Forced alignment | Custom Viterbi on CTC
emissions | in-house". The NC-licensed shortcuts are excluded by §4.2 and §7.

Why the tests lean on *structural* properties rather than golden numbers: the guarantees
downstream code needs from an aligner are that spans are monotone, non-overlapping, and
complete. §5's sentence anchors are derived from these spans, and the Stage 5 hard invariant
(`final_in <= anchor_in`) is only meaningful if the anchors are trustworthy.
"""

from __future__ import annotations

import math
import random
from itertools import pairwise

import pytest

from hawedit.forced_alignment import (
    AlignmentInfeasible,
    align_words,
    greedy_ctc_tokens,
    minimum_frames,
    viterbi_align,
)

BLANK = 0


def emissions(frames: list[dict[int, float]], vocab: int = 4) -> list[list[float]]:
    """Build a log-probability matrix. Unlisted tokens get a low log-probability."""
    matrix: list[list[float]] = []
    for frame in frames:
        row = [math.log(0.01)] * vocab
        for token, probability in frame.items():
            row[token] = math.log(probability)
        matrix.append(row)
    return matrix


# --- feasibility is checked before anything is aligned --------------------------------


def test_minimum_frames_counts_the_blanks_repeats_require() -> None:
    """CTC needs a blank between two identical tokens, so `aa` needs three frames."""
    assert minimum_frames([1, 2]) == 2
    assert minimum_frames([1, 1]) == 3
    assert minimum_frames([1, 1, 1]) == 5
    assert minimum_frames([1, 2, 2, 3]) == 5


def test_fewer_frames_than_tokens_is_refused() -> None:
    with pytest.raises(AlignmentInfeasible, match="frames"):
        viterbi_align(emissions([{1: 0.9}]), [1, 2], blank_id=BLANK)


def test_a_repeated_token_without_room_for_its_blank_is_refused() -> None:
    with pytest.raises(AlignmentInfeasible, match="frames"):
        viterbi_align(emissions([{1: 0.9}, {1: 0.9}]), [1, 1], blank_id=BLANK)


def test_empty_tokens_are_refused() -> None:
    with pytest.raises(ValueError, match="token"):
        viterbi_align(emissions([{1: 0.9}]), [], blank_id=BLANK)


def test_empty_emissions_are_refused() -> None:
    with pytest.raises(ValueError, match="emission"):
        viterbi_align([], [1], blank_id=BLANK)


def test_ragged_emissions_are_refused() -> None:
    """A ragged matrix means the caller mixed up frames and vocabulary somewhere upstream."""
    with pytest.raises(ValueError, match="width"):
        viterbi_align([[0.0, -1.0], [0.0]], [1], blank_id=BLANK)


def test_a_token_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(ValueError, match="vocabulary"):
        viterbi_align(emissions([{1: 0.9}], vocab=2), [7], blank_id=BLANK)


def test_a_blank_id_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(ValueError, match="blank"):
        viterbi_align(emissions([{1: 0.9}]), [1], blank_id=99)


# --- the alignment itself --------------------------------------------------------------


def test_a_clear_two_token_case_lands_where_the_evidence_is() -> None:
    matrix = emissions(
        [
            {1: 0.9},
            {1: 0.9},
            {1: 0.9},
            {2: 0.9},
            {2: 0.9},
            {2: 0.9},
        ]
    )
    spans = viterbi_align(matrix, [1, 2], blank_id=BLANK)
    assert [(s.token_id, s.start_frame, s.end_frame) for s in spans] == [(1, 0, 2), (2, 3, 5)]


def test_every_token_receives_at_least_one_frame() -> None:
    """A token with no frames would produce a zero-length word and a broken caption."""
    matrix = emissions([{1: 0.9}] * 8, vocab=5)
    spans = viterbi_align(matrix, [1, 2, 3], blank_id=BLANK)
    assert len(spans) == 3
    for span in spans:
        assert span.end_frame >= span.start_frame


def test_spans_are_monotone_and_never_overlap() -> None:
    """Everything downstream — sentence anchors, captions, EDL — assumes time moves forward."""
    matrix = emissions([{1: 0.8}, {1: 0.6}, {2: 0.7}, {2: 0.9}, {3: 0.8}, {3: 0.6}], vocab=5)
    spans = viterbi_align(matrix, [1, 2, 3], blank_id=BLANK)
    for earlier, later in pairwise(spans):
        assert earlier.end_frame < later.start_frame


def test_spans_are_returned_in_token_order() -> None:
    matrix = emissions([{1: 0.9}, {2: 0.9}, {3: 0.9}], vocab=5)
    spans = viterbi_align(matrix, [1, 2, 3], blank_id=BLANK)
    assert [s.token_id for s in spans] == [1, 2, 3]


def test_a_repeated_token_is_separated_by_a_blank() -> None:
    """The CTC rule that makes this a real algorithm rather than an argmax."""
    matrix = emissions([{1: 0.9}, {BLANK: 0.9}, {1: 0.9}])
    spans = viterbi_align(matrix, [1, 1], blank_id=BLANK)
    assert spans[0].end_frame < spans[1].start_frame
    assert spans[0].start_frame == 0
    assert spans[1].end_frame == 2


def test_blank_frames_belong_to_no_token() -> None:
    matrix = emissions([{1: 0.9}, {BLANK: 0.95}, {BLANK: 0.95}, {2: 0.9}])
    spans = viterbi_align(matrix, [1, 2], blank_id=BLANK)
    assert spans[0].end_frame == 0
    assert spans[1].start_frame == 3


def test_scores_are_finite_log_probabilities() -> None:
    matrix = emissions([{1: 0.9}, {2: 0.9}], vocab=4)
    for span in viterbi_align(matrix, [1, 2], blank_id=BLANK):
        assert math.isfinite(span.mean_logprob)
        assert span.mean_logprob <= 0.0


def test_confident_evidence_scores_better_than_weak_evidence() -> None:
    strong = viterbi_align(emissions([{1: 0.99}, {2: 0.99}]), [1, 2], blank_id=BLANK)
    weak = viterbi_align(emissions([{1: 0.30}, {2: 0.30}]), [1, 2], blank_id=BLANK)
    assert strong[0].mean_logprob > weak[0].mean_logprob


# --- words, times, and the §5 contract -------------------------------------------------


def test_words_carry_millisecond_timings_from_the_frame_rate() -> None:
    matrix = emissions([{1: 0.9}, {1: 0.9}, {2: 0.9}, {2: 0.9}], vocab=4)
    words = align_words(
        matrix, [("ئەمە", [1]), ("باشە", [2])], frame_duration_ms=20.0, blank_id=BLANK
    )
    assert [(w.w, w.start_ms, w.end_ms) for w in words] == [
        ("ئەمە", 0, 40),
        ("باشە", 40, 80),
    ]


def test_a_word_end_is_exclusive_of_the_next_word_start() -> None:
    """Adjacent words must not claim the same millisecond, or a clip boundary is ambiguous."""
    matrix = emissions([{1: 0.9}, {2: 0.9}], vocab=4)
    words = align_words(
        matrix, [("یەک", [1]), ("دوو", [2])], frame_duration_ms=10.0, blank_id=BLANK
    )
    assert words[0].end_ms <= words[1].start_ms


def test_a_multi_token_word_spans_all_of_its_tokens() -> None:
    matrix = emissions([{1: 0.9}, {2: 0.9}, {3: 0.9}], vocab=5)
    words = align_words(
        matrix, [("کوردستان", [1, 2]), ("جوانە", [3])], frame_duration_ms=100.0, blank_id=BLANK
    )
    assert (words[0].start_ms, words[0].end_ms) == (0, 200)
    assert (words[1].start_ms, words[1].end_ms) == (200, 300)


def test_word_confidence_is_a_probability() -> None:
    matrix = emissions([{1: 0.9}, {2: 0.9}], vocab=4)
    for word in align_words(
        matrix, [("a", [1]), ("b", [2])], frame_duration_ms=20.0, blank_id=BLANK
    ):
        assert 0.0 < word.conf <= 1.0


def test_a_word_with_no_tokens_is_refused() -> None:
    with pytest.raises(ValueError, match="token"):
        align_words(emissions([{1: 0.9}]), [("", [])], frame_duration_ms=20.0, blank_id=BLANK)


def test_aligned_words_satisfy_invariant_5_when_stored() -> None:
    """The output must be storable as a transcript — which requires the ctc_viterbi aligner."""
    from hawedit.transcripts import AsrProvenance, RawTranscript

    matrix = emissions([{1: 0.9}, {2: 0.9}], vocab=4)
    words = align_words(
        matrix, [("ئەمە", [1]), ("باشە", [2])], frame_duration_ms=20.0, blank_id=BLANK
    )
    transcript = RawTranscript(
        media_id="m",
        text_ckb="ئەمە باشە",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    assert len(transcript.words) == 2


# --- refusals that nothing was checking -------------------------------------------------
#
# M1.1's row claims "infeasible input refused rather than guessed". Audited 2026-08-09: the
# whole infeasibility chain inside `viterbi_align` — the unreachable-end-state check, the
# backtracking dead-end check and the every-token-framed check — could be deleted together and
# all 1,099 tests stayed green, while the function degraded from raising `AlignmentInfeasible`
# to raising a bare `KeyError: 0`. `frame_duration_ms <= 0` and the no-tokens word refusal were
# likewise untested. D-079.
#
# The three checks inside the chain are mutually redundant on purpose: remove any one and
# another catches the same condition, so a single-guard mutation is expected to survive. What
# had to be pinned is the refusal itself, and that it is the *documented* exception rather than
# whatever falls out of a broken path.


def test_emissions_that_cannot_emit_the_tokens_are_refused_not_guessed() -> None:
    """A token with -inf in every frame has no path. Refusal is the contract; KeyError is not.

    Deleting the three infeasibility checks turns this into `KeyError: 0` from the span
    assembly, which no caller could interpret and no downstream stage could detect.
    """
    impossible = [[0.0, -math.inf, -math.inf] for _ in range(10)]
    with pytest.raises(AlignmentInfeasible) as raised:
        viterbi_align(impossible, [1], blank_id=0)
    assert "cannot emit" in str(raised.value)

    # No path anywhere, not merely for the token.
    with pytest.raises(AlignmentInfeasible):
        viterbi_align([[-math.inf] * 3 for _ in range(10)], [1], blank_id=0)
    # Two tokens, neither reachable.
    with pytest.raises(AlignmentInfeasible):
        viterbi_align(impossible, [1, 2], blank_id=0)


def test_a_feasible_alignment_is_still_produced() -> None:
    """The control. A `viterbi_align` that raised unconditionally passes the test above.

    Same shape of input as the impossible case, with the token reachable instead of -inf.
    """
    possible = [[0.0, -1.0, -1.0] for _ in range(10)]
    spans = viterbi_align(possible, [1], blank_id=0)
    assert len(spans) == 1
    assert spans[0].start_frame <= spans[0].end_frame


def test_a_non_positive_frame_duration_is_refused() -> None:
    """Frames per millisecond is the scale on every word time; zero silently collapses them."""
    emissions = [[0.0, -1.0, -1.0] for _ in range(10)]
    for duration in (0, -5, -0.001):
        with pytest.raises(ValueError, match="frame_duration_ms must be positive"):
            align_words(emissions, [("ڕۆژ", [1])], frame_duration_ms=duration)


def test_a_word_carrying_no_tokens_is_refused() -> None:
    """A word with no acoustic evidence cannot be timed, and a zero-length span captions air."""
    emissions = [[0.0, -1.0, -1.0] for _ in range(10)]
    with pytest.raises(ValueError, match="has no tokens"):
        align_words(emissions, [("ڕۆژ", [])], frame_duration_ms=20)
    # And when it is one word among several, so the refusal is not order-dependent.
    with pytest.raises(ValueError, match="has no tokens"):
        align_words(emissions, [("ڕۆژ", [1]), ("باش", [])], frame_duration_ms=20)


def test_a_positive_frame_duration_still_times_words() -> None:
    """The control for the two refusals above: neither may be a function rejecting everything."""
    emissions = [[0.0, -1.0, -1.0] for _ in range(10)]
    words = align_words(emissions, [("ڕۆژ", [1]), ("باش", [2])], frame_duration_ms=20)
    assert len(words) == 2
    assert words[0].end_ms <= words[1].start_ms


# --- D-135: CTC's own hypothesis, from the same posteriors ---------------------------------


def _row(vocabulary: int, best: int, weight: float = 0.9) -> list[float]:
    """One frame's log-probabilities, peaked on `best`."""
    rest = math.log((1.0 - weight) / (vocabulary - 1))
    return [math.log(weight) if index == best else rest for index in range(vocabulary)]


def test_the_greedy_decode_collapses_repeats_and_drops_blanks() -> None:
    """Standard CTC greedy decoding, which is what "CTC-3B's hypothesis" means.

    Frames: 1 1 blank 1 2 2 blank 3 — the two runs of 1 are separated by a blank, so both
    survive; the run of 2 collapses to one; blanks never appear in the output.
    """
    blank = 0
    frames = [1, 1, blank, 1, 2, 2, blank, 3]
    emissions = [_row(4, best) for best in frames]
    assert greedy_ctc_tokens(emissions, blank_id=blank) == (1, 1, 2, 3)


def test_a_repeat_with_no_blank_between_collapses_to_one() -> None:
    """The control for the test above: without the separating blank, CTC reads one token.

    A decode that kept both would emit doubled letters throughout, which looks like a plausible
    transcription and would make every segment disagree with the LLM.
    """
    emissions = [_row(4, best) for best in [1, 1, 1, 1]]
    assert greedy_ctc_tokens(emissions, blank_id=0) == (1,)


def test_an_all_blank_segment_decodes_to_nothing() -> None:
    """Silence is a real answer. `escalation.materially_disagree` treats one empty side as the
    strongest disagreement, so this must be empty rather than invented."""
    assert greedy_ctc_tokens([_row(4, 0) for _ in range(6)], blank_id=0) == ()


def test_the_decode_follows_the_posteriors_and_not_the_frame_order() -> None:
    """The discriminating control: a decode that returned frame indices, or the argmin, or a
    constant would satisfy the assertions above on some input. Here the peak moves.
    """
    emissions = [_row(5, best) for best in [3, 3, 0, 4, 0, 1]]
    assert greedy_ctc_tokens(emissions, blank_id=0) == (3, 4, 1)
    # Same frames, peaks inverted within the vocabulary: the answer must move with them.
    inverted = [[row[-1 - i] for i in range(len(row))] for row in emissions]
    assert greedy_ctc_tokens(inverted, blank_id=4) == (1, 0, 3)


def test_a_ragged_or_empty_matrix_is_refused() -> None:
    with pytest.raises(ValueError, match="empty posterior matrix"):
        greedy_ctc_tokens([], blank_id=0)
    with pytest.raises(ValueError, match="ragged"):
        greedy_ctc_tokens([[0.0, -1.0], [0.0]], blank_id=0)
    with pytest.raises(ValueError, match="outside the vocabulary"):
        greedy_ctc_tokens([[0.0, -1.0]], blank_id=7)


def test_the_decode_can_produce_a_token_the_reference_text_never_used() -> None:
    """Why the decode runs on the **full** vocabulary, before `_align_emissions` compacts it.

    `asr._align_emissions` projects the posteriors onto only the columns the LLM's own tokens
    occupy. Decoding from that matrix would confine CTC to the LLM's vocabulary, so the two
    hypotheses could differ only in order — a substituted word, the case §3's disagreement
    trigger exists for, would be unreachable.

    Here the acoustic peak is on token 4, which the reference text's tokens (1, 2) do not
    include: the full decode finds it, and a compacted decode cannot.
    """
    full = [_row(5, best) for best in [1, 0, 4, 0, 2]]
    assert greedy_ctc_tokens(full, blank_id=0) == (1, 4, 2)

    reference_tokens = [0, 1, 2]  # blank plus what the LLM said
    compacted = [[row[column] for column in reference_tokens] for row in full]
    compacted_ids = greedy_ctc_tokens(compacted, blank_id=0)
    assert 4 not in {reference_tokens[i] for i in compacted_ids}, (
        "the compacted decode reached a token outside the reference, so this test is not "
        "measuring the restriction it names"
    )


# --- D-170: an oracle that does not share the implementation's reasoning ---------------------
#
# Everything above is a hand-written expectation. They are good tests and they share one
# weakness: a systematic misreading of CTC would be written into the code *and* into the
# numbers beside it, and every one of them would still pass. What was missing is an
# independent answer to the same question.
#
# This is exhaustive search — every legal state path enumerated and scored, no dynamic
# programming, no shared reasoning with `viterbi_align` beyond the CTC transition rule itself.
# Exponential, so it runs on small matrices; that is where boundary errors live anyway.
#
# Cross-checked once against torchaudio's reference kernel on 259 matrices (0 disagreements,
# `evidence/an-aligner-with-no-independent-oracle.md`). The dependency stays out of the suite:
# `pyproject.toml` avoids torchaudio deliberately ("WAV frames to tensor without torchaudio")
# and it reaches the gate only transitively, so leaning the gate on it would be a supply-chain
# decision taken for a test's convenience.


_ORACLE_TOLERANCE = 1e-9
# One inclusive frame range per token, in token order — what both answers reduce to.


_Spans = tuple[tuple[int, int], ...]


def _extended(tokens: list[int]) -> list[int]:
    states = [BLANK]
    for token in tokens:
        states.extend((token, BLANK))
    return states


def _legal(states: list[int], previous: int, state: int) -> bool:
    """Stay, advance one, or skip a blank between two *different* tokens."""
    if state in (previous, previous + 1):
        return True
    if state == previous + 2:
        return states[state] != BLANK and states[state] != states[state - 2]
    return False


def _all_paths(matrix: list[list[float]], tokens: list[int]) -> dict[_Spans, float]:
    """Every legal path's span tuple, mapped to the best score that reaches it."""
    states = _extended(tokens)
    frames = len(matrix)
    found: dict[_Spans, float] = {}

    def walk(frame: int, state: int, score: float, path: list[int]) -> None:
        if frame == frames:
            if state not in (len(states) - 1, len(states) - 2):
                return
            spans: dict[int, list[int]] = {}
            for index, visited in enumerate(path):
                if visited % 2 == 1:
                    spans.setdefault((visited - 1) // 2, [index, index])[1] = index
            if len(spans) != len(tokens):
                return  # a path that never entered some token's state emits a shorter sequence
            key = tuple((spans[i][0], spans[i][1]) for i in range(len(tokens)))
            found[key] = max(found.get(key, -math.inf), score)
            return
        for nxt in range(state, min(state + 3, len(states))):
            if _legal(states, state, nxt):
                walk(frame + 1, nxt, score + matrix[frame][states[nxt]], [*path, nxt])

    for start in (0, 1):
        if start < len(states):
            walk(1, start, matrix[0][states[start]], [start])
    return found


def _oracle(matrix: list[list[float]], tokens: list[int]) -> tuple[set[_Spans], int]:
    """The span tuples an exhaustive search finds optimal, and how many were legal at all."""
    paths = _all_paths(matrix, tokens)
    if not paths:
        return set(), 0
    best = max(paths.values())
    return {key for key, score in paths.items() if score >= best - _ORACLE_TOLERANCE}, len(paths)


def _pseudorandom_matrix(
    seed: int, frames: int, vocab: int, blank_weight: float
) -> list[list[float]]:
    """Deterministic log-probabilities. Seeded so a failure is reproducible, never flaky.

    `blank_weight` is here because real CTC posteriors are blank-dominated — silence and
    inter-phone frames outnumber emitting ones — and a corpus of flat random rows is a
    distribution this aligner never sees. Measured: once blanks dominate, the best path changes
    shape, and over 50,683 such matrices a token-skipping path outscores every legal one on
    **34,932** of them, so the completeness check is doing real work there.

    Recorded honestly: it was added chasing a mutation that turned out to be a no-op, and it
    changed no result in the audit (D-170). It is kept for the distribution argument alone.
    """
    rng = random.Random(seed)
    matrix: list[list[float]] = []
    for _ in range(frames):
        weights = [rng.uniform(0.05, 1.0) for _ in range(vocab)]
        weights[BLANK] *= blank_weight
        total = sum(weights)
        matrix.append([math.log(w / total) for w in weights])
    return matrix


def _oracle_cases() -> list[tuple[int, list[list[float]], list[int]]]:
    rng = random.Random(20260811)
    cases = []
    for seed in range(60):
        vocab = rng.randint(3, 5)
        frames = rng.randint(2, 9)
        tokens = [rng.randint(1, vocab - 1) for _ in range(rng.randint(1, 4))]
        # Silence is the common case in real speech, so the corpus has to contain it: a
        # flat-blank corpus is blind to the whole class of "step over a token" errors.
        blank_weight = rng.choice([1.0, 1.0, 20.0, 200.0])
        cases.append((seed, _pseudorandom_matrix(seed, frames, vocab, blank_weight), tokens))
    return cases


def test_the_aligner_agrees_with_an_exhaustive_search_of_every_legal_path() -> None:
    """The dynamic program must find a path the brute force also calls optimal.

    Membership rather than equality: two paths can score identically, and requiring one
    particular tie-break would pin an implementation detail rather than the answer.
    """
    checked = 0
    for seed, matrix, tokens in _oracle_cases():
        optimal, _ = _oracle(matrix, tokens)
        if not optimal:
            with pytest.raises(AlignmentInfeasible):
                viterbi_align(matrix, tokens, blank_id=BLANK)
            continue
        spans = viterbi_align(matrix, tokens, blank_id=BLANK)
        mine = tuple((s.start_frame, s.end_frame) for s in spans)
        assert mine in optimal, (
            f"seed {seed}, tokens {tokens}: the aligner returned {mine}, which an exhaustive "
            f"search of every legal CTC path does not rank best. Optimal: {sorted(optimal)}"
        )
        checked += 1
    assert checked >= 40, f"only {checked} cases were actually aligned; the corpus went vacuous"


def test_the_exhaustive_search_rejects_paths_as_well_as_accepting_them() -> None:
    """The control. An oracle that calls everything optimal agrees with any aligner at all.

    For every case with more than one legal path, the optimal set must be a **strict** subset
    of them — so the test above is comparing against a real preference and not against
    "anything goes".
    """
    discriminating = 0
    for seed, matrix, tokens in _oracle_cases():
        optimal, legal_paths = _oracle(matrix, tokens)
        if legal_paths <= 1:
            continue
        assert len(optimal) < legal_paths, (
            f"seed {seed}, tokens {tokens}: the oracle ranks all {legal_paths} legal paths "
            f"equally optimal, so it would accept any aligner"
        )
        discriminating += 1
    assert discriminating >= 40, (
        f"only {discriminating} cases had a choice to make; the corpus no longer exercises the "
        f"oracle's ability to reject"
    )
