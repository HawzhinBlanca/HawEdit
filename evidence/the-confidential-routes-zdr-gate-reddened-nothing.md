# The confidential route's ZDR gate reddened nothing

> Measured 2026-08-10 on hawapc01 against `e2c768f`, Python 3.11 in `.venv`, no credentials of any
> kind — every call goes through an injected transport.

§3 Stage 3 on confidential material: *"for COMMS and KAAE material, paid tier and Vertex with ZDR
are mandatory, not advisory — 100% of the transcript leaves the network."* `tests/test_gemini.py`'s
own docstring calls this "the only one with legal consequences".

`Governance` implements it with **two** methods:

| gate | guards | refusal tests |
|---|---|---|
| `assert_permits_upload` | the Gemini **Developer API** | 4 |
| `assert_permits_vertex` | the **confidential Vertex route** | **0** |

## Measured

Each gate neutered in turn — body replaced by `return` — against a baseline verified green first,
whole gate suite each time:

```
baseline green: True

held    the Developer API gate stops refusing (assert_permits_upload)
          red: test_claimed_zero_data_retention_must_name_who_confirmed_it,
               test_confidential_material_without_zero_data_retention_is_refused,
               test_counting_tokens_cannot_send_confidential_text_before_the_zdr_gate,
               test_flags_cannot_turn_the_developer_api_into_a_confidential_vertex_route

UNHELD  the confidential Vertex gate stops refusing (assert_permits_vertex)

restored and green: True
```

`grep -rn "assert_permits_vertex" tests/` → **0 hits**. Every `Governance(` in `tests/` builds a
`GeminiJudge` except one: the fully permitted Vertex triple, which asserts the call *succeeds*.

## The artifact

With the Vertex gate neutered, a judge built the way a confidential job builds it:

```python
VertexGeminiJudge("client-project", governance=Governance(confidential=True), …)
judge.judge(request_with_the_client_transcript_and_real_keyframes)
```

```
HTTP calls: 2
  projects/client-project/locations/global/publishers/google/models/gemini-2.5-pro:countTokens
    confidential transcript present in the prompt: True
    source JPEG bytes present: True
  projects/client-project/locations/global/publishers/google/models/gemini-2.5-pro:generateContent
    confidential transcript present in the prompt: True
    source JPEG bytes present: True
```

A verdict came back. `zero_data_retention` was `False` and `confirmed_by` was empty. 1,440 tests
were green throughout.

## And it contradicts a recorded claim

`PROGRESS.md` M2.8, from adversarial pass #20:

> Everything in `gemini.py` survived the pass — … the retry ceiling and **the ZDR gate all redden
> when reverted**.

True of `assert_permits_upload`. False of `assert_permits_vertex`. Pass #20 reverted the gate it
could see, and there were two.

## The fix

D-145 built `_concrete_judges()` — every constructible judge class, bound bidirectionally to
`GeminiJudge`'s transitive subclasses — to hold the §7 model-identity check. Its builders now take
an optional `governance` and a `transport`, so the same enumeration is built under every
confidential state §3 forbids:

* zero-data-retention not configured
* claimed but unattributed
* attributed with whitespace only
* **attributed, but ZDR still not configured** — the state the first version missed

for both judge classes, at `judge()`, `count_parts()` and `generate_json()`. Each case asserts the
refusal **and** `api.urls == []`: `pytest.raises` alone is satisfied by a gate that raises after the
upload, and the failure mode here is the bytes, not the traceback.

The control is the other half: every judge must still reach the API and return a verdict for
material that needs no confirmation, with `api.urls` non-empty — otherwise a gate hoisted to refuse
everything, or a transport that never sends, would pass every test above.

## Proof

```
baseline green: True

RED  the defect restored: the confidential Vertex gate stops refusing
RED  Vertex stops requiring zero-data-retention (rule one only)
RED  Vertex accepts an unattributed confirmation (rule two only)
RED  Vertex accepts whitespace as an attribution
RED  judge() stops checking governance before the billed call
RED  count_request_tokens stops checking governance before counting
RED  count_parts stops checking governance before counting
RED  generate_json stops checking governance before generating
RED  VertexGeminiJudge stops overriding _assert_governance (uses the parent's gate)
RED  the enumeration stops naming VertexGeminiJudge, so its gate is unheld again

10/10
restored and green: True
```

**The first pass was 6/8, and both survivors were real gaps in my table rather than bad mutations.**
Deleting the ZDR rule entirely was invisible because every forbidden state I had listed also lacked
an attribution, so the second rule caught them all. Deleting `generate_json`'s check was invisible
because its only caller in `src/` calls `count_parts` first. Both are now their own tests.

## A measurement of mine was wrong first

The sweep that started this iteration appended ` and False` to each condition. `ruff` flags that as
**SIM223**, so every mutation broke the lint step, the nested-gate test saw a non-4 exit, and all
fourteen guards reported "held" — each naming the same unrelated test. A uniform result across
unrelated mutations is an artifact, not a finding. Redone by deleting each statement whole by its
AST line span, with the lint status printed beside every result so a contaminated run says so
itself.

## Measured and not fixed here

Twelve of the fourteen argv refusals in `_run_from_args` are unheld: deleting the `if`/`raise`
outright leaves all 1,440 tests green.

```
held: 2   unheld: 12
  UNHELD  --transcript and --omni-asr are mutually exclusive Stage 1 sources
  UNHELD  --omni-asr-runtime and --wsl-distro require --omni-asr
  UNHELD  --gemini and --vertex-project are mutually exclusive cloud routes
  UNHELD  cloud judging and --verdict are mutually exclusive Stage 4 sources
  UNHELD  cloud discovery requires --transcript or --omni-asr
  UNHELD  --sentences requires --transcript or --omni-asr
  UNHELD  --verdict requires a Stage 1 source and --sentences
  UNHELD  --visual requires --transcript or --omni-asr
  UNHELD  --qc-pass requires --sentences or --auto-select
  UNHELD  --auto-select requires --transcript or --omni-asr
  UNHELD  --timelens and --face-reframe require --sentences or --auto-select
  UNHELD  governance flags apply only with a Gemini or Vertex route
```

`test_the_cli_refuses_flags_whose_prerequisites_are_absent` looks like coverage for three of them
and asserts only `main([...]) == 2` — the exit code for *every* caught exception, so it passes
whether the refusal fires or the run merely dies later on an empty `source.mp4`. Next increment.

Gate: `VERIFY OK — hawedit gate green`, 1453 tests (floor 1440 → 1453).
