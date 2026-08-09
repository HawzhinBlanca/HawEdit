# §3 Stage 1's second escalation trigger had no input

> Measured 2026-08-10 on hawapc01 against `36a5f3c`.

M1.4's named shortfall, written by D-109: *"`select_for_validation` still cannot be called, because
`ctc_text` is **never** computed — the CTC pass yields emissions for alignment and nothing decodes
them — and the validator it routes to is `BLOCKED.md` #16."*

§3 Stage 1 has two triggers. The quartile got its input in D-109. This is the other one.

## Reproduced

```
$ grep -rn "ctc_text" src/
src/hawedit/escalation.py:57   ctc_text: str                       (the dataclass field)
src/hawedit/escalation.py:81   ctc_text: str,                      (the predicate's parameter)
src/hawedit/escalation.py:88   if not llm_text.strip() or not ctc_text.strip():
src/hawedit/escalation.py:91       return llm_text.strip() != ctc_text.strip()
src/hawedit/escalation.py:92   return normalized_cer(llm_text, ctc_text) >= threshold_cer
src/hawedit/escalation.py:117  disagrees = materially_disagree(segment.llm_text, segment.ctc_text, …)
```

Six mentions, all inside the module that consumes it. Nothing produces it. And
`select_for_validation` had **no caller in `src/` at all** — only tests.

**Never computed**, not computed and discarded: `transcribe_segment` held the posteriors and spent
them on timing the LLM's words.

## The fix, and the one judgement in it

A greedy CTC decode of the same posteriors: argmax per frame, repeats collapsed, blanks dropped. No
model, no download, no threshold — D-015 already chose `DEFAULT_DISAGREEMENT_CER = 0.15`.

The judgement is **which matrix**. `_align_emissions` projects the posteriors onto only the columns
the LLM's own tokens occupy. Decoding from that would confine CTC to the LLM's vocabulary, so the
hypotheses could differ only in order and a substituted word — the case the trigger exists for —
would be unreachable. `test_the_decode_can_produce_a_token_the_reference_text_never_used` builds a
matrix whose peak is a symbol the reference does not contain and requires it to survive.

## The rule runs on the real artifact

```
$ python -m hawedit.pipeline "…/ZAR38MinTest.mp4" --work-dir … --transcript … --json

escalation.scored_segments: 545
escalation.escalated:       136          (= 545 // 4)
threshold:                  0.15
segments listed:            136
   4802-6302   True | bottom-quartile confidence (mean logprob -10.310)
   8002-8926   True | bottom-quartile confidence (mean logprob -8.350)
  11202-13086  True | bottom-quartile confidence (mean logprob -10.471)
```

Every reason names the quartile, because that transcript predates this change and carries no
hypotheses. Two empty sides read as **agreement**, not as disagreement — so an old artifact
escalates on confidence alone instead of escalating all 545. That is the honest reading and it is
pinned by a test.

## The performance defect in this change's own first version

The decode was written as a pure Python function over the emissions. Measured on a 200-frame segment
against a 32,000-token vocabulary:

```
                                   per segment      across 547 segments
  .tolist() on the full matrix        182.9 ms            100.0 s
  Python argmax over the vocabulary   210.3 ms            115.0 s
  tensor.argmax(dim=-1).tolist()        2.03 ms              1.1 s
```

~215 s of CPU against 1.1 s. Split: `collapse_ctc_path` is O(frames), pure and model-agnostic;
`_ctc_hypothesis` takes the argmax in torch where the tensor lives. A test hands it a wrapper that
**raises** on `.tolist()` of the full matrix, so the fast path is a property rather than a comment.

## Proof

```
baseline green: True

RED  the runner stops applying §3's escalation rule (the defect: no caller in src/)
RED  the artifact stops carrying the CTC hypothesis, so disagreement cannot be computed
RED  the LLM hypothesis is dropped from the artifact instead
RED  transcribe_segment stops decoding CTC at all
RED  the greedy decode keeps blanks
RED  the greedy decode stops collapsing repeats
RED  the decode takes the argmin instead of the best path
RED  the torch fast path takes the argmin instead
RED  _ctc_hypothesis materialises the whole posterior matrix again (the ~215 s route)
RED  the report stops saying which trigger fired
RED  scores_from_transcript loses the per-segment identity, collapsing the quartile
RED  the report omits the escalation section

12/12
restored and green: True
```

**The first pass was 6/9** — on the nine mutations that existed before the torch fast
path and the `by_trigger` breakdown added three more — and all three survivors were the same class: the decode, the scores and
the wiring were tested; the *carrying* was not. Blanking either hypothesis where
`SegmentConfidence` is built, or skipping the decode entirely, left five suites green. Closing the
last one needed a fake **one layer lower than any existing test** — every backend double replaces
`transcribe_segment` itself, so the method that calls the decode was never driven. That is D-118's
`read_scenes` finding repeated exactly.

### The real-weights run, and what it changed

The full `--omni-asr` run finished after this was first written: **1,547 s** on hawapc01's two
3090 Ti, 545 segments, a 1,070,637-byte report. **542 of 545 segments carry a real CTC hypothesis**,
so the decode works on real weights. What it produced is the finding:

```
first script of each CTC hypothesis, over 542 segments
  ARABIC        428  ( 79.0%)      CJK            11  (  2.0%)
  LATIN          96  ( 17.7%)      MALAYALAM/HEBREW/CYRILLIC/DEVANAGARI/BENGALI  7  (1.3%)

LLM: کاکە بیلال                              CTC: കക بില                       CER 0.800
LLM: کەشوو مشتەز و بەخێوی زارکلاس …          CTC: ت زور خب انجاي اكثر حظ كم    CER 0.640
LLM: باسی گیم وڵکنیوزم بۆ بکەی               CTC: paseki molknusen bopka       CER 0.960
```

**CTC-3B's greedy decode is unconditioned.** The LLM pass is called with `lang=["ckb_Arab"]`; a
greedy argmax over the acoustic model's full multilingual vocabulary is conditioned on nothing, so a
sixth of the hypotheses are not even in Arabic script. The confound lands exactly on D-015's bar:

```
normalized CER, LLM vs CTC, all 542 hypotheses        median 0.167   (above the 0.15 bar)
                             Arabic-script only (428) median 0.125   (below it), 175/428 over
escalated on the real run    312 / 545 = 57%
  disagreement only   176      both   116      quartile only   20
```

**So the input exists and the comparison is not yet meaningful.** §3's rule is implemented as
written, with D-015's recorded threshold, and it escalates 57% of the file — where the quartile
alone is 25% by construction. 176 segments escalate on disagreement alone, and the median CER moves
from *above* the bar to *below* it once script-mismatched hypotheses are excluded, which is what
shows the confound is deciding rather than colouring the outcome.

**Not fixed here, and deliberately not guessed.** Restricting the decode to a "Kurdish subset" of the
vocabulary means naming which of ~32,000 tokens are Kurdish; conditioning the CTC pass the way the
LLM pass is conditioned is a modelling change whose effect on §8.1 is unmeasured; and lifting the
threshold to swallow the confound would be a guessed number chosen to make an output look right.
Each is a decision about which segments get validator time. `BLOCKED.md` #19.

**What the code does in the meantime:** computes and carries the hypotheses (real data, honestly
labelled), applies §3's rule as written, and reports **which trigger fired** —
`by_trigger: {quartile_only, disagreement_only, both}` — so the 312 can never be read as §3's
validated routing. A bare total would have been exactly that.

## Also found

**Found in passing, not fixed here:** a `--omni-asr` run killed mid-flight leaves
`stage1/omni-asr-request.json` behind, and the next run refuses with a bare
`[Errno 17] File exists: …omni-asr-request.json`. The refusal is correct — it is the same
class D-132 closed for Stage 0's extraction sidecar, where a run that dies must leave no record —
but the message does not say what to delete, and nothing cleans it up.

Gate: `VERIFY OK — hawedit gate green`, 1355 tests.
