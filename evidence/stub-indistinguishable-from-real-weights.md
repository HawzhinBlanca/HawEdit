# A stub with no model produced a §8.1 report identical to the real adapter's

> Measured 2026-08-09 on hawapc01 against `a3e0d00`, against a green 1,168 baseline.

M0.7's row says "every measurement names its adapter class", and it did — `type(adapter).__name__`.
The hard rule it is there to satisfy is stronger: *a number carries the hardware and adapter that
produced it*. A class name asserts an adapter; it does not carry one.

`validate_adapter` resolves `adapter.model_id` against §7, so a stub has to claim a real §7 model id
— and claiming one is free. After that the class name was the only remaining signal.

## Measured

A stub named exactly like the canonical adapter, with no weights, no GPU and no backend:

```python
class OmniAsrAdapter:
    model_id = "omniASR_LLM_7B_v2"
    def transcribe(self, audio_path, duration_s):
        return ASRResult(text_raw=PERFECT)
```

Through `run_benchmark`, the emitted §8.1 report:

```
the stub's own identity:
   class name         : OmniAsrAdapter
   module-qualified   : __main__.OmniAsrAdapter

the real adapter's identity:
   class name         : OmniAsrAdapter
   module-qualified   : hawedit.asr.OmniAsrAdapter

what the report says produced these numbers:
   adapter_impls      : ['OmniAsrAdapter']
   normalized_cer     : 0.0
   mean_rtf           : 0.1
   hardware           : {'accelerator': '2x RTX 3090 Ti', 'host': 'hawapc01', 'notes': ''}

distinguishable from the real adapter in the artifact: False
```

A perfect CER and a 0.1 real-time factor, attributed to `2x RTX 3090 Ti` on a named host, from a
class that loaded nothing. Byte for byte what a real run emits.

Never computed rather than computed-and-discarded: the module was never read, so there was nothing to
discard.

## The fix

One site — `asr.py` builds every `Measurement`, and it is the only place in `src/` that derives an
adapter identity (grepped: the other six `type(...).__name__` uses are all error messages).

```python
adapter_impl=f"{type(adapter).__module__}.{type(adapter).__name__}",
```

`test_bench.OmniAsrAdapter` carries where the code came from; `OmniAsrAdapter` only asserts it. The
module is a fact about the object in hand, not a lookup, which matters — resolving a revision by
model id would have made the stub look *more* real, since it claims a genuine §7 id and the pinned
SHA would be returned for it.

Measured, not assumed: under pytest the module reads `test_bench` rather than `tests.test_bench`,
because there is no `tests/__init__.py`. The tests assert the literal string that actually appears.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   back to the bare class name (the defect)                              FAILED=4
CAUGHT   a constant prefix that identifies nothing (the plausible wrong fix)    FAILED=3
CAUGHT   the module without the class                                          FAILED=4
CAUGHT   the adapter is not named at all                                       FAILED=4

4/4
```

The two new tests are complementary rather than redundant, which the audit shows precisely:

* The **constant-prefix** mutation — `f"hawedit.asr.{type(adapter).__name__}"`, which satisfies "it
  has a module now" while identifying nothing — is caught by the stub test and **not** by the
  control, because for the real class a constant `hawedit.asr.` prefix produces exactly the right
  answer.
* **Module-without-class** is caught by the control, which pins the real adapter's own qualified
  name so the fix cannot be satisfied by a string that merely looks qualified.

The control is a real measurement of `hawedit.asr.OmniAsrAdapter` with a backend that raises — no
weights needed, because M0.7's "failures are recorded not raised" means the measurement is still
produced and still carries its adapter. That property is now load-bearing for this test as well.

## What this does not close

**Substituting the backend inside the real adapter.** `OmniAsrAdapter(backend=...)` is a public
constructor parameter, and a fake backend behind the genuine class still reports
`hawedit.asr.OmniAsrAdapter`. This fix closes class substitution, which is what was measured; it does
not identify the weights.

Recording the backend was rejected rather than forgotten: `backend` is not part of the `ASRAdapter`
protocol, so reading it would be a special case keyed on one class's internals, and `Measurement`
sees only the adapter. Identifying the weights properly means the protocol exposing what it loaded —
a design step, not a side effect of this one. Named here so the gap is visible rather than implied.

Gate: `VERIFY OK — 1170 passed, 0 skipped`.
