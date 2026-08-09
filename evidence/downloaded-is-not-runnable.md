# The readiness report said OK for a checkpoint nothing on this machine can load

> Measured 2026-08-09 on hawapc01 against `18e0509`, against a green 1,172 baseline.

M1.4 is PARTIAL, and its named shortfall said the way was clear:

> the real rzgar validator is not yet invoked by this producer — its weights **are** present on this
> machine (10.1 GB, `python -m hawedit.models` reports `OK`), so what is missing is the composition,
> not the download

I picked that row to close. The premise did not survive contact.

## Measured

The environment is genuinely capable, which is what made the row plausible:

```
torch 2.13.0+cu130   cuda available: True   devices: 2
transformers 4.57.6  accelerate present
models/rzgar__qwen3-asr-sorani-kurdish-ckb-v1/model.safetensors   4,076,191,640 bytes
```

The loader is not:

```
config.json  architectures: ['Qwen3ASRForConditionalGeneration']   model_type: qwen3_asr
transformers.Qwen3ASRForConditionalGeneration      : NO
transformers.models.qwen3_asr                      : ModuleNotFoundError
AutoModel can map 'qwen3_asr'                      : False
qwen model modules present: colqwen2, qwen2, qwen2_5_omni, qwen2_5_vl, qwen2_audio,
                            qwen2_moe, qwen2_vl, qwen3, qwen3_moe, qwen3_next,
                            qwen3_omni_moe, qwen3_vl, qwen3_vl_moe
```

`config.json` names `transformers_version: 4.57.6` — the version that is installed — and that version
still cannot load it. The checkpoint's own model card says why:

> `from qwen_asr import Qwen3ASRModel  # pip install qwen-asr`

A separate package. So **the composition is not what is missing**: the loader is, and no amount of
wiring in `asr.py` would have changed that. Had I written the adapter first, it would have been code
that cannot run, tested against a stub — the exact shape this repo keeps finding and refusing.

Never computed rather than computed-and-discarded: nothing ever tried to import a loader, so there was
nothing to discard.

## The root defect

`hawedit.models` classifies each §7 component by how it arrives, and the weights branch asked one
question — is the directory non-empty. `_PIP_MODULES` already exists for components whose *runtime* is
the gating fact, but it is consulted only for `Provisioning.PIP` entries. A checkpoint that needs both
a download **and** a loader had no way to say so.

That is why the report printed `OK   rzgar/... weights (10.1 GB)`, and why a careful row written from
that report concluded the wrong thing in prose. The artifact is read as "can this stage run"; it was
answering "is it on disk".

```
before:  OK   rzgar/qwen3-asr-sorani-kurdish-ckb-v1   weights   weights from rzgar/... (10.1 GB)
         10/15 available

after:   MISS rzgar/qwen3-asr-sorani-kurdish-ckb-v1   weights   weights from rzgar/... are on disk,
              but the loader 'qwen_asr' is not installed — the checkpoint cannot be loaded here, so
              this component cannot run  (10.1 GB)
         9/15 available
```

9/15 is the truer number. The size is still reported: the weights really are there, and an operator
deciding what to fetch needs to know they need not fetch them again.

## Not installed, deliberately

`pip install qwen-asr` would have flipped the report green in one command. It was not run:

* A new runtime dependency needs a licence under D-002 and a pin plus checksum under the supply-chain
  rule. `BLUEPRINT.md` §7 records the *model's* licence (Apache 2.0); the loader package is a separate
  artifact whose licence I have not read.
* CI installs `.[dev,media]`, so a locally-installed package would make the local gate and the gate of
  record disagree about which program they are testing — the exact failure D-092 and D-093 were about.
* It is Hawa's call whether this project takes a dependency, and it belongs in a decision with the
  licence quoted, not in a loop iteration's side effect.

Recorded in `BLOCKED.md` #16 with the measurement, rather than worked around.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the runtime check never fires (the defect)                     FAILED=2
CAUGHT   any declared runtime marks the component unavailable           FAILED=1
CAUGHT   the check runs but does not reach `available`                  FAILED=2
CAUGHT   the validator's loader requirement is dropped from the map     FAILED=1

4/4
```

The second is the over-strict direction and it is caught **only** by the control. Without it,
"every entry in the runtime map reports MISS" satisfies every other test here and would retire three
components that demonstrably load today — VideoChat3-4B, TimeLens2-4B and the Qwen embedding pair,
each with decoded-frame evidence behind M5.4 and M6.3.

The fourth matters for a different reason: the map's content is evidence from the model card, and
dropping the entry is the cheapest way to make the report green again. It is caught by the test that
asserts the *coupling* — the validator is available exactly when `qwen_asr` imports — rather than
today's answer, so it holds in CI (where the loader is also absent) and would keep holding the day
someone installs it.

Gate: `VERIFY OK — 1175 passed, 0 skipped`.
