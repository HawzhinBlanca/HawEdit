# Optional runtime security and reproducibility — 2026-08-09

## Finding

The GPU and cloud extras were not reproducible. `accelerate>=1.0`, `pillow>=10`,
`torchvision>=0.28`, and `google-auth>=2.40,<3` allowed a later install to change the runtime
underneath the real-model and Vertex measurements. The development pin was also
`pytest==8.3.4`, which `pip-audit` reports as affected by PYSEC-2026-1845 (fixed in 9.0.3).

The measured GPU environment already contained the current direct versions, so the runtime pins
were closed to facts rather than guesses:

| extra | package | exact version |
|---|---|---:|
| dev | pytest | 9.1.1 |
| gpu | transformers | 4.57.6 |
| gpu | accelerate | 1.14.0 |
| gpu | pillow | 12.3.0 |
| gpu | torchvision | 0.28.0 |
| cloud | google-auth | 2.56.3 |

PyPI's index reported these as the current releases on 2026-08-09. The exact pins make direct
dependency resolution repeatable; they do **not** claim a hash-locked transitive runtime. That
larger lock remains separate from the hash-locked release builder recorded in D-090.

## Transformers 4.57.6: scanner result and VEX

A clean all-extras environment still makes `pip-audit==2.9.0` report four Transformers
advisories. This is not rewritten as “no vulnerabilities found.” Transformers 5.x cannot replace
the pin blindly: D-055 measured three VideoChat3 incompatibilities, including a silently random
`lm_head`, and changed reranker scores and order. Each advisory was therefore checked against
the code HawEdit actually executes.

| advisory | scanner finding | HawEdit disposition |
|---|---|---|
| PYSEC-2026-2289 / CVE-2026-4372 | Private attention/expert config fields can name and execute a Hub kernel while bypassing `trust_remote_code`. | **Mitigated in code.** Every HawEdit-owned Transformers path recursively rejects both private fields and repository-shaped public implementation fields before importing or calling a processor/config/model loader. |
| PYSEC-2026-2290 / CVE-2026-5241 | LightGlue can propagate a config-supplied `trust_remote_code` into a nested loader. | **Not reachable and independently mitigated.** Config-supplied `trust_remote_code` is rejected recursively, and each adapter allowlists only the exact nested `model_type` values in its measured checkpoint. `lightglue` is refused. |
| PYSEC-2025-217 / CVE-2025-14929 | Malicious X-CLIP checkpoint conversion can deserialize attacker data. | **Not reachable.** HawEdit has no X-CLIP import or conversion call, and adapter model-type allowlists reject `xclip` before dispatch. |
| PYSEC-2026-2288 / CVE-2026-1839 | `Trainer._load_rng_state()` can load a malicious pickle on PyTorch below 2.6. | **Not reachable on two independent facts.** HawEdit never imports or constructs `Trainer`, and the pinned runtime is PyTorch 2.13.0, above the advisory's unsafe `<2.6` condition. |

Primary advisory/fix sources:

- <https://github.com/advisories/GHSA-29pf-2h5f-8g72>
- <https://github.com/huggingface/transformers/commit/a7f8e7f>
- <https://github.com/advisories/GHSA-fgcw-684q-jj6r>
- <https://github.com/huggingface/transformers/commit/676559d>
- <https://github.com/advisories/GHSA-69w3-r845-3855>

The guard is in `hawedit.models.assert_transformers_config_safe`. It runs from the shared visual
loader before CUDA discovery and from `QwenSoraniValidator` before importing Qwen-ASR. The real
checkpoint configs on hawapc01 were read with the production guard and all passed with these exact
allowlists:

```text
MCG-NJU__TimeLens2-4B                    qwen3_vl, qwen3_vl_text
MCG-NJU__VideoChat3-4B                   qwen3, videochat3
Qwen3-VL-Embedding-2B                    qwen3_vl, qwen3_vl_text
Qwen3-VL-Reranker-2B                     qwen3_vl, qwen3_vl_text
rzgar__qwen3-asr-sorani-kurdish-ckb-v1  qwen3_asr, qwen3_asr_audio_encoder,
                                         qwen3_asr_text, qwen3_asr_thinker
```

Regressions cover nested private fields, both public remote-kernel fields, nested
`trust_remote_code`, X-CLIP/LightGlue model-family substitution, malformed/missing configs, the
visual loader's pre-runtime ordering, and the Stage 1 validator path.

## Clean all-extras proof

An isolated Python 3.12.13 environment was created at `.gate/dependency-audit-d094` and installed
from this checkout with `.[dev,media,cloud,gpu]`. It resolved the exact direct versions above plus
`torch==2.13.0`. Results:

```text
pip check
No broken requirements found.

torch       2.13.0+cpu
torchaudio  2.11.0+cpu
silero-vad  5.1.2
# all three import successfully; Stage 0 uses Silero's pinned ONNX backend.

scripts/verify.sh
Ruff:       passed
mypy:       100 source files, passed
format:     100 files, passed
pytest:     1237 passed, 0 skipped, 96.83 s
evidence:   1237 collected, 1237 passed, 0 skipped
VERIFY OK   (109.4 s outer command; warm dependency/type caches)
```

Installing `google-auth` exposed one environment-dependent mypy failure at its untyped
`Credentials.refresh` method. `untyped_calls_exclude` now names that one external method; strict
checking remains active for the rest of `gemini.py` and the project. The exact exclusion is pinned
by `tests/test_dependency_security.py` because base CI does not install the cloud extra.

The clean audit reports no advisory in any installed third-party package except the four
Transformers records dispositioned above. The local editable `hawedit` distribution is skipped by
`pip-audit` because it is not published on PyPI.
