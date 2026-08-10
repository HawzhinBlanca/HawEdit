# BLOCKED — needs Hawa

The only legitimate reason to stop the loop. Everything here is a hard external dependency:
no amount of engineering on this machine resolves it.

Environment this was **originally** assessed in: cloud container, no GPU, no ffmpeg, no client
media, no API credentials. Python 3.11, PyPI reachable.

**Re-assessed 2026-08-08 on hawapc01, and the machine is not that machine.** Two entries below
were blockers of the environment, not of the project, and they do not hold here. Measured:

| Fact | Value |
|---|---|
| Hostname | `HAWAPC01` — §6's box |
| GPU | 2 × NVIDIA GeForce RTX 3090 Ti, 24564 MiB each (§6's "2×24 GiB"), driver 596.36 |
| ffmpeg | 8.1.1-full on `PATH`, `--enable-libass --enable-libharfbuzz --enable-libfribidi --enable-nvenc` |
| `huggingface.co` | **200** (was: refused by proxy) |
| `commonvoice.mozilla.org` · `www.openslr.org` · `zenodo.org` | **200** (were: refused by proxy) |
| OS | Windows 11 Pro — see D-044, six defects the project had never met |

An entry keeps its heading after it is resolved; the record of what was in the way is worth
more than a tidy file, and `tests/test_claims.py` reads "resolved" off the heading.

---

## #1 · Labelled Sorani audio set — blocks M0.12, M0.13, and therefore all of M0

**What §8.1 requires:** several hours of Central Kurdish audio with reference transcripts,
labelled across **Hewlêr · Slemani · Mukriyan · formal news · casual podcast · ckb–English
and ckb–Arabic code-switching · noisy environments · overlapping speakers · named entities
and political terminology.**

**Why it blocks:** §8.1 is titled "blocks everything" and §10 lists "Sorani CER unmeasured on
your dialects" as risk #1. The harness can be built and unit-tested without audio; the
*numbers* cannot be produced, and every downstream threshold (escalation quartile in §3
Stage 1, quality gates in M7) is derived from them. Per §4.4 a single aggregate CER is not
an acceptable substitute — the set must carry per-dialect labels or the metric hides the
dialect the product is used in.

**What unblocks it, in order of preference:**
1. Your own labelled material (client or archive footage) with reference transcripts.
2. Pointer to an existing annotated Sorani set you already trust.
3. ~~Authorisation to bootstrap from a public Sorani corpus (e.g. Common Voice `ckb`) as an
   *interim* set.~~ **Authorised in D-012 and now closed — see below.** It was read speech:
   it would have exercised the harness end-to-end on genuinely real Kurdish audio without
   satisfying the podcast / overlapping-speaker / dialect split §8.1 asks for, so it could
   only ever de-risk M0, not close it.

### Option 3 closed, 2026-08-08 — the interim route no longer exists publicly

`BLOCKED.md` #6 tracked whether the authorised corpus was *reachable*, and from hawapc01 every
host answers 200. That turned out to be the wrong question. Searched and measured, not assumed:

| Source | Finding |
|---|---|
| Common Voice `ckb` on Hugging Face | `mozilla-foundation/common_voice_17_0` is now a **stub**. Its README: *"Effective October 2025, Mozilla Common Voice datasets are now exclusively available through Mozilla Data Collective"* |
| `datacollective.mozillafoundation.org` | Needs an account and accepted terms. Creating an account and accepting terms on your behalf is not something I will do — that is yours to click |
| OpenSLR | Reachable, and **156 resources parsed, 0 Kurdish**. There is no Kurdish set there |
| `facebook/omnilingual-asr-corpus` | Ungated, CC-BY-4.0, and the natural match for §7's own ASR — but the released repo carries **348 languages / 349 configs and no `ckb`**. §7's "ckb_Arab CER 6.0" is a figure about the *model*; the corpus subset Meta published does not include ckb |
| `akam-ot/sorani-tts` | Real Sorani audio with reference text, 5.7K clips, ungated — and **no licence at all**. D-002 makes that a hard reject, not a judgement call |
| `roshna-omer/common_voice_16_0_*_ckb_*` | Common Voice 16 ckb re-uploads, ungated — but **metadata only**: 23 columns of `path`/`text`/`snr`/`pitch`, no `Audio` feature, 766 KB for 5,000 rows. No audio to transcribe, and no licence either |

So there is currently **no ungated, licensed, reference-transcribed Sorani audio corpus** this
machine can fetch. The importer (M0.14) is built and tested and has nothing to import.

**Any one of these reopens it:**

1. **You accept Mozilla Data Collective's terms and download Common Voice `ckb`.** Point me at
   the extracted directory — `validated.tsv` plus `clip_durations.tsv` from the *same* release —
   and `import_common_voice` takes it from there. It refuses a non-`ckb` locale and refuses to
   run without the durations file, so a wrong download fails loudly rather than quietly.
2. **Your own footage**, which is option 1 above and worth more than any of this.
3. **Authorise `akam-ot/sorani-tts` despite the missing licence.** I am recording it rather than
   recommending it: D-002's rule is no data without a licence, this ships to clients, and TTS
   read speech is further from §8.1's conditions than Common Voice was.

Until then M0.16 is BLOCKED again, on #1 rather than on #6. I marked it TODO earlier today on
the strength of the hosts answering — that was true and it was not the question.

---

## #2 · hawapc01 (or any GPU) — **RESOLVED 2026-08-08**

**Resolved: this checkout is on hawapc01.** Hostname `HAWAPC01`, two RTX 3090 Ti at 24564 MiB
each — the 2×24 GiB §6 describes and the layout §3 Stage 1 assumes (`LLM_7B` on GPU 0 at
~17 GiB, `CTC_3B` on GPU 1 at ~8 GiB). NVENC is compiled into the ffmpeg on `PATH`, so M3.3's
second shortfall has its hardware too.

What this does **not** resolve: the weights themselves are a separate fact (see #6, now also
resolved for reachability, and the source-id question below it), and a measurement still has to
be *run* before M0.13 can be marked. The GPU stopped being the reason.

Original entry, kept for the record:

## #2 (original) · hawapc01 (or any GPU) — blocks M0.11, M0.13

Real ASR adapters need `omniASR_LLM_7B_v2` (~17 GiB VRAM) and `omniASR_CTC_3B_v2` (~8 GiB).
This container has no GPU. Two specific consequences:

- §8.1 requires **"real-time factor measured on hawapc01"**, and §3 Stage 1 explicitly warns
  that Meta's published RTF (0.003 / 0.092) is A100 batch=1 BF16 and must not be turned into
  wall-clock promises for the 3090 Ti. A number measured anywhere else is the wrong number.
- Peak VRAM and long-audio failure rate are hardware-specific in the same way.

The harness measures all three through an adapter interface, so this is a matter of running
it on the right box, not of writing more code. **Needed:** a way to run on hawapc01, or
confirmation that I should ship the harness and you run it.

---

## #3 · Gemini API credentials — blocks the Gemini candidate in M0, and all of M4

- §8.1 lists **Gemini 2.5 Pro native audio** as a benchmark candidate.
- §4 pins `KURDISH_EDITORIAL_JUDGE = gemini-2.5-pro`.
- §3 Stage 3 / §10: before the first client job, Path A requires **paid tier + Vertex with
  zero-data-retention configured** — this is called "mandatory, not advisory" because full
  transcripts leave the network. That is a governance decision, not a config value.

**Needed:** whether to target the Developer API or Vertex, and the credential path. I will not
put a key in the repo; it goes through env (`.env` is on the never-edit list).

### Measured 2026-08-07 — a key exists and the project has no paid tier

A Developer API key was supplied and stored through `python -m hawedit.credentials`. It
authenticates: **50 models visible, `gemini-2.5-pro` among them.** The live check then failed
on the first real call:

```
Quota exceeded for metric: generate_content_free_tier_requests,
limit: 0, model: gemini-2.5-pro
```

**A free-tier limit of exactly zero.** `gemini-2.5-pro` is paid-tier only, so the pinned §4
judge cannot be called at all until billing is enabled on the key's Google Cloud project.

This is the distinction the credential panel could not make on its own and `smoke.py` exists
for: a key can be *valid*, and the model it is pinned to can be *visible in the listing*, and
neither of those means it is callable. A listing is not a capability — the same lesson as
`encoder_available` refusing to trust ffmpeg's `-encoders` output (D-028).

Nothing was billed; both calls were rejected before generation. The retry path behaved
correctly — three attempts on the 429, then a refusal naming the reason rather than a crash or
an invented verdict.

Isolated with a two-model probe on the same key, seconds apart:

```
gemini-2.5-flash   HTTP 200 — call succeeded
gemini-2.5-pro     HTTP 429 — free_tier_requests, limit: 0
```

So the key, the network path and the API are all fine. The project is on the free tier and the
**pinned** judge is the one model with no free-tier allowance.

**A Google AI Ultra subscription does not cover this.** That is a consumer plan for the Gemini
app; `generativelanguage.googleapis.com` bills through the Cloud billing account attached to
the API key's project. Credits on the consumer plan are not spendable on the API surface.

**To unblock:** link a billing account to the key's Cloud project (AI Studio → the key → its
project). No new key is needed. This is required by §3 regardless of convenience: paid tier
plus Vertex zero-data-retention is "mandatory, not advisory" before the first client job,
because full-transcript discovery sends 100% of every transcript to Google. The governance half
of this entry is still open and still needs a name, not a flag.

**Not a workaround:** `gemini-2.5-flash` answers on this key today. Routing the judge to it
would produce a green run and would be a measurement of a different system — §4 pins
`gemini-2.5-pro`, §7's registry refuses substitution, and §8.1 is explicit that figures from
different models are not comparable. Flash was a diagnostic and is not wired to anything.

---

## #4 · Hugging Face gated-repo acceptance — blocks M0.10, M1 diarization

`pyannote/speaker-diarization-community-1` is a **gated** repo (§3 Stage 0 flags this and
asks that the access-acceptance step be built into deployment automation). Its CC-BY-4.0
attribution notice also has to appear in shipped product docs.

**Needed:** an HF account with the licence accepted, and its token available to the
deployment environment.

---

## #5 · ffmpeg with libass + HarfBuzz + FriBidi — **RESOLVED 2026-08-06**

**Resolved.** `scripts/fetch-ffmpeg.sh` obtains a verified build (n8.0.1, libass +
HarfBuzz + FriBidi) via the Git-LFS media endpoint, which the proxy allows even though
`github.com` is denied. The golden render now runs inside the gate, and Kurdish invariant
#4 is fully enforced — see `evidence/rtl-shaping.md` and D-021. The binary is ~200 MB and
git-ignored; run the fetch script once per checkout.

Original entry, kept for the record:

## #5 (original) · ffmpeg with libass + HarfBuzz + FriBidi

Not installed here. §4.3 requires `shaping=complex` **and** a libass actually built with
HarfBuzz — the blueprint is explicit that a build accepting the option may still lack the
backing library, which is why §4.3.6 mandates a golden-file render test in CI rather than
trusting the flag.

Recording it now so M3 does not discover it late. Unblocking this is likely just an install
in the render image, but the golden reference PNG must be generated on a build whose libass
is verified — so the first reference has to come from a trusted box, not from whatever
ffmpeg a CI runner happens to ship.

---

## #6 · The interim corpus is authorised but not reachable — **RESOLVED 2026-08-08**

**Resolved: every host in the table below answers 200 from hawapc01.** `huggingface.co`,
`commonvoice.mozilla.org`, `www.openslr.org` and `zenodo.org` are all reachable. The network
policy was the container's, not this machine's.

Two things it does **not** resolve, and they are the ones now in the way:

1. **Two of the four unnamed §7 checkpoints still have no repository id.** Reaching the network
   does not supply one — a host you can 404 against is not progress. The two Qwen entries are
   now resolved and configured; `omniASR_LLM_7B_v2` and `omniASR_CTC_3B_v2` are **#10**, which
   this entry was masking.
2. **The gated repo still needs an accepted licence and a token** — that is #4, untouched.

Original entry, kept for the record:

## #6 (original) · The interim corpus is authorised but not reachable — network policy

**Status:** Hawa authorised a public Sorani corpus as an interim set (D-012). The importer
is built and tested (M0.14). **The data cannot be downloaded from this container.**

Measured at the agent proxy, not guessed:

| Host | Result |
|---|---|
| `huggingface.co` | connection refused by proxy |
| `datasets-server.huggingface.co` | `403` to CONNECT (policy denial) |
| `commonvoice.mozilla.org` | connection refused by proxy |
| `www.openslr.org` | connection refused by proxy |
| `zenodo.org` | connection refused by proxy |
| `github.com` / `raw.githubusercontent.com` | reachable |
| `pypi.org` | reachable |

This blocks the interim audio run **and** M0.11's model weights, which also live on Hugging
Face — so no ASR model can be obtained here either, which is why an end-to-end interim CER
is not merely missing a corpus.

**Any one of these unblocks it:**

1. **Allow `huggingface.co` in the environment's network policy.** Both the corpus and the
   §7 model weights come from there. This is the single change that unblocks the most.
2. **Point me at a corpus on GitHub.** GitHub is reachable, so a repo or release asset works
   today — give me `owner/repo` and I will pull and import it. I have deliberately not gone
   hunting: guessing repository names is how the wrong dataset gets imported, and the
   importer refuses a non-`ckb` locale precisely because that mistake is silent.
3. **Commit the audio to this repo** (or a repo I can read) if it is small enough.

What was delivered without it: the importer, and a real measurement of §4.1 collision
incidence on the only real Sorani reachable here — KLPT's bundled 24,894-entry lexicon
(`evidence/collision-incidence.md`, D-013).

---

## #7 · The hawedit CI job is not a *required* status check — **RESOLVED 2026-08-08**

**Resolved: `gate` is now a required status check on `main`.** Hawa supplied the GitHub CLI and
authorised the change; it was made only after the runner went green, so `main` was never protected
against a check that was failing.

```
required_checks: ["gate"]   strict: true   allow_force_pushes: false   allow_deletions: false
```

`strict: true` means a branch must be up to date with `main` before merging, so the check runs
against what will actually land. `enforce_admins` is left **off** deliberately: this is a
single-maintainer repository and locking the owner out of their own `main` in an emergency buys
nothing here. That is a judgment call and it is the one part of this a second pair of eyes might
change.

**What it cost to get here, which is the part worth keeping.** The requirement could not be
switched on honestly until the runner was green, and it was not: `mypy --strict` had been failing
there since the first Stage 2 commit (D-067), four stub tests only ran on a CUDA machine (D-068),
and a skipped stage had stopped naming its blocker. Three commits, all of them defects this
machine could not see. The entry below said "treat every DONE mark as resting on a local run plus
an advisory CI run" — that sentence was carrying more weight than anyone had checked.

Original entry, kept for the record:

**Needs:** Hawa, in the GitHub repository settings. One click, no code.

`.github/workflows/gate.yml` now runs the gate on a clean runner — audit finding #5 was
that nothing ever did. But a workflow that runs is not a workflow that blocks: until `gate`
is added to the protected branch's required status checks, a red run is a red tick beside a
mergeable PR.

This matters more here than it usually would, because the project's own definition of DONE is
"verify.sh green **AND** required CI checks green". The second half of that sentence currently
refers to nothing.

**To unblock:** Settings → Branches → branch protection rule for the default branch → Require
status checks to pass → add **`gate`** (workflow `gate`).

Until then, treat every DONE mark as resting on a local run plus an advisory CI run.

**Measured 2026-08-08, and it is no longer hypothetical.** With `gh` available, the remote gate turned out to have been **red since 14:07** while `verify.sh` printed VERIFY OK here — `mypy --strict` fails on a runner that does not install the `gpu` extra, on four lines added across four iterations. Nothing in the repository could tell, because the workflow runs without blocking and nobody had looked. Fixed in D-067, and the gate now runs the type checker in the runner's condition so the two cannot diverge silently again — but the *structural* gap this entry describes is untouched: a red run is still a red tick beside a mergeable PR.

---

## #8 · §3 Stage 4 and §5 disagree about two judge outputs — **RESOLVED 2026-08-07**

**Resolved.** Hawa delegated the choice; §5 gains both fields, additively and optionally, so no existing §5 document breaks. `payoff_at_ms` in `editorial`, `hashtags_ckb` in `output` — see D-033 for the reasoning. **`BLUEPRINT.md` itself still needs Hawa's amendment**: it is frozen and implementation work does not edit it, so the code is deliberately ahead of the spec in this one recorded place.

Original entry, kept for the record:

## #8 (original) · §3 Stage 4 and §5 disagree about two judge outputs

**Needs:** Hawa, one decision. No code, no credentials.

§3 Stage 4 lists **payoff location** and **hashtags** among the judge's outputs. §5's frozen
JSON contract has no cell for either. `narrative_role` records *that* a clip is a payoff, not
*where* the payoff lands.

This does not block Stage 4 — the verdict carries both and the projection to §5 drops them
explicitly (D-030), so nothing is lost inside the pipeline. It blocks knowing what the client
artifact is supposed to contain.

**The question:** does §5's contract gain `payoff_at_ms` and `hashtags_ckb`, or is §3 Stage 4's
output list aspirational? Both readings are defensible and I will not pick one — §5 is frozen,
and editing it is redesigning the architecture rather than implementing it.

Until it is answered, a payoff location and hashtags exist in every verdict and stop at §5's
boundary.

## #9 · §9's M8 names two models §7 does not contain

**Needs:** Hawa, one decision. No code, no credentials, no hardware.

§9's build order ends with `M8 · Auto-reframe (SAM 3 / Molmo2)`. Neither **SAM 3** nor
**Molmo2** appears anywhere in §7's model registry, and §7 is the table this project treats as
closed: `registry.py` refuses any model not in it, and `tests/test_registry.py` parses §7 out
of `BLUEPRINT.md` and asserts set equality **both ways**, so a model added in code but not in
the blueprint fails the gate. That check is deliberate and it is working — it means M8 cannot
be started, not that the check is wrong.

§3 Stage 6 also makes SAM 3 conditional rather than planned: "Vertical reframing tracks the
active speaker from diarization plus face detection; **add SAM 3 only if face-centred cropping
proves insufficient on real footage**." So M8 has two gates, and neither is code:

1. Real Kurdish footage showing that face-centred cropping is insufficient (`BLOCKED.md` #1).
   Until that measurement exists, §3 says not to add the model at all.
2. A §7 amendment naming SAM 3 and Molmo2 with their licences, if step 1 says they are needed.

**The question:** does §7 gain those two rows, and with which licences? Molmo2 in particular
needs a licence check before anything else — a NonCommercial licence is a hard reject in this
project and would end the question there.

Until both clear, M8 stays TODO and is not startable. Recorded here rather than left as an
ordinary backlog row, because "not started" and "cannot be started" are different facts and
this project does not let those serialize to the same thing.

---

## #10 · §7's two omniASR checkpoints do not exist under the names §7 gives them — **ANSWERED 2026-08-08**

**Answered by Hawa: `_v2` names the published checkpoints.** `omniASR_LLM_7B_v2` is
`facebook/omniASR-LLM-7B` and `omniASR_CTC_3B_v2` is `facebook/omniASR-CTC-3B`. Both are
configured in `models/sources.json`, which records that they are a decision rather than a
lookup so nobody later mistakes them for verified name matches the way the two Qwen entries
beside them are.

**`BLUEPRINT.md` §7 still carries the `_v2` cells.** The blueprint is frozen and implementation
work does not edit it, so the code is deliberately ahead of the spec in a second recorded place
— the same arrangement as #8 / D-033. `tests/test_registry.py` is unaffected: it asserts §7's
*model ids* against the registry, and the repository id lives in `sources.json`, which §7 does
not describe.

**This did not make Stage 1 runnable, and the reason is new — see D-046.** The two checkpoints
are single raw fairseq2 `.pt` files (31.2 GB and 12.3 GB) with a SentencePiece tokenizer and no
`config.json`, so `transformers` cannot load them; they need `omnilingual-asr`, which needs
`fairseq2`, which needs `fairseq2n` — a compiled native extension published **only** as
`manylinux_2_28_x86_64` and `macosx_14_0_arm64` wheels. hawapc01 is Windows. That is recorded
as **#11**, because it is a different question from this one and answering this one exposed it.

Original entry, kept for the record:

## #10 (original) · §7's two omniASR checkpoints do not exist under the names §7 gives them

**Needs:** Hawa, one decision. No credentials, no hardware — and, now, no network excuse.

This was invisible while #6 was live. "The weights are unreachable" and "we do not know which
repository the weights are in" produce the same symptom — no model on disk — and the first
masked the second. With `huggingface.co` reachable from hawapc01, only the second is left.

§7 names four components as *checkpoint names* rather than repository ids. Two resolve exactly
and are now configured in `models/sources.json`, verified rather than guessed:

| §7 name | Repository | Evidence |
|---|---|---|
| `Qwen3-VL-Embedding-2B` | `Qwen/Qwen3-VL-Embedding-2B` | exact name match, official `Qwen` namespace, `license:apache-2.0` — the licence §7 records — 1.1M downloads |
| `Qwen3-VL-Reranker-2B` | `Qwen/Qwen3-VL-Reranker-2B` | exact name match, same namespace and licence, 580K downloads |

**The other two do not resolve.** §7 says `omniASR_LLM_7B_v2` and `omniASR_CTC_3B_v2`. Meta
publishes thirteen omniASR checkpoints under `facebook/` — `omniASR-LLM-{300M,1B,3B,7B}`,
`omniASR-LLM-7B-ZS`, `omniASR-CTC-{300M,1B,3B,7B}`, `omniASR-W2V-{300M,1B,3B,7B}`, all
Apache-2.0 — and **not one carries a `_v2` suffix**. The sizes and roles §7 wants exist
(`facebook/omniASR-LLM-7B`, `facebook/omniASR-CTC-3B`); the version marker in their §7 names
does not.

Two readings, and they are not equivalent:

1. `_v2` is an internal or in-repo checkpoint name and §7 means the published checkpoints. Then
   the mapping is `omniASR_LLM_7B_v2 → facebook/omniASR-LLM-7B` and `omniASR_CTC_3B_v2 →
   facebook/omniASR-CTC-3B`.
2. `_v2` denotes a genuinely different, later checkpoint — in which case downloading the
   published ones gives a model that loads, runs, produces plausible Sorani, and is **not the
   model §8.1's numbers would be about**. That failure is silent, and it contaminates every
   threshold derived from the benchmark.

Reading 2 is why this is not being decided here. D-022's rule was written against a 404 at 3am;
this is worse than a 404, because it succeeds. §7 is also the table `tests/test_registry.py`
parses out of the frozen `BLUEPRINT.md` and asserts set equality against, so the names cannot be
changed in code alone.

**The question:** does §7's `_v2` mean `facebook/omniASR-LLM-7B` and `facebook/omniASR-CTC-3B`,
or does it name something else? If the former, either amend §7's cells or say the word and the
mapping goes into `models/sources.json` citing this entry.

Until answered, `omniASR_LLM_7B_v2` and `omniASR_CTC_3B_v2` have no source, `models.py` refuses
to invent one, and §3 Stage 1 cannot run — which keeps M1.4, M0.11 and M0.13 open.

---

## #11 · §7's canonical ASR cannot be loaded on Windows — **RESOLVED 2026-08-08**

**Resolved in code by choosing WSL2 for Stage 1 on Windows.** `--omni-asr` now selects a
path-confined Windows→WSL worker automatically; `hawedit-asr-setup` (wrapped by
`scripts/setup-wsl-asr.ps1` in a checkout) provisions a source-fingerprinted Python 3.12 runtime
under the user's local app-data, installs official `omnilingual-asr`, and refuses a setup without
both CUDA GPUs. Stage 0 and WAV cutting stay on the host, one worker loads both models
once, and the returned `RawTranscript` is validated before the immutable store accepts it.
Direct Linux execution remains available through `--omni-asr-runtime local`. This resolves the
architecture/runtime blocker, not the missing labelled Sorani corpus or an unrun 44 GB model
pair; those remain measurement blockers under #1.

**Needs:** Hawa, one decision — where §3 Stage 1 runs. No credentials, no purchase.

Answering #10 supplied the repository ids and immediately produced a different obstacle. This
is not a naming question and not a network question; it is a platform one, and it is the last
thing standing between this project and a transcript.

**What the checkpoints actually are.** `facebook/omniASR-LLM-7B` and
`facebook/omniASR-CTC-3B` are not `transformers` repositories. Each is a single raw
`.pt` file plus a SentencePiece tokenizer, and nothing else:

| Repo | Files | Size |
|---|---|---|
| `facebook/omniASR-LLM-7B` | `omniASR-LLM-7B.pt`, `omniASR_tokenizer_v7.model`, README | **31.2 GB** |
| `facebook/omniASR-CTC-3B` | `omniASR-CTC-3B.pt`, `omniASR_tokenizer.model`, README | **12.3 GB** |

No `config.json`, no `model.safetensors`, no processor config, and the Hub reports
`library: None`. `AutoModel` has nothing to dispatch on. The model card points at
`facebookresearch/omnilingual-asr`, which is the loader.

**Why that loader will not install here.** Measured on PyPI, not assumed:

- `omnilingual-asr` 0.2.0 requires `fairseq2[arrow] >=0.5.2,<=0.6.0`, and `requires_python`
  is `>=3.10,<=3.12`.
- `fairseq2` requires `fairseq2n`, a compiled native extension.
- `fairseq2n` publishes wheels for **`manylinux_2_28_x86_64`** and **`macosx_14_0_arm64`**.
  There is no Windows wheel, and no pure-Python fallback — it is a C++/CUDA extension.

So on Windows the canonical Sorani ASR is a 31 GB file with no loader. Note what this does
*not* mean: `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` — §3 Stage 1's **validator** — is a normal
`safetensors` repo and loads fine here, as do every Stage 2/3/5 model. This is specific to the
two models §7 makes canonical, which is the worst place for it.

**WSL2 is on this machine and it works.** Measured, not assumed:

| Fact | Value |
|---|---|
| Distro | Ubuntu 26.04 LTS, WSL 2, already running |
| GPU inside WSL | `nvidia-smi` reports **both** RTX 3090 Ti at 24564 MiB, driver 596.36 — CUDA passthrough is live |
| Disk inside WSL | 740 GB free on `/` |
| ffmpeg inside WSL | 8.0.1 |
| Python inside WSL | **3.14.4 — too new.** `omnilingual-asr` caps at 3.12 |

`docker-desktop` is also registered as a WSL distro, so a container is a second route.

**The question — three shapes, and it is an architecture choice, not a preference:**

1. **Stage 1 runs in WSL2** on this box: install a 3.12 there (deadsnakes or `uv`), plus
   `omnilingual-asr` and CUDA torch. §6 says Stage 1 runs on hawapc01's GPUs and this satisfies
   that literally — same hardware, same driver. It splits the pipeline across two environments,
   so `asr.Hardware` has to record which one produced a number, and §8.1's "RTF measured on
   hawapc01" needs a decision about whether WSL2 counts as hawapc01 for that purpose. My
   reading is that it does — same silicon, same driver — but that is a measurement-provenance
   claim and this project does not let me make it quietly.
2. **Stage 1 runs in a Linux container** with GPU passthrough. Cleaner isolation, reproducible,
   and the natural shape if §6's "server" ever stops being this desktop. More moving parts.
3. **Stage 1 runs on a Linux host** and hawapc01 does Stage 0 and Stage 6. Matches §6's
   split most closely and needs hardware that is not here.

Until one is chosen, M0.11, M0.13 and M1.4 stay open: the weights are identified, downloadable
and licensed Apache-2.0, and nothing on this OS can open them.

**Not blocked by this:** every other §7 model. Stage 2's embedder and reranker, Stage 3 Path B,
Stage 5's TimeLens2 and the Stage 1 validator are all ordinary `transformers` repositories that
load natively on Windows, and they are being integrated regardless.

---

---

## #12 · Two sessions share this checkout, and the history no longer says who decided what

> **Refreshed 2026-08-09 (D-075).** The shared-index half of this is gone: the second agent now
> works on its own branch (`codex/production-readiness-20260809`, `576dfed`, CI green, no PR
> open) and `main` no longer changes under this session. The failure mode moved rather than
> ended — from silently reverting each other's files to silently **duplicating each other's
> work**. Both branches independently implemented Hugging Face revision pinning within the same
> day, agreeing on all four visual-checkpoint SHAs and disagreeing on where they live
> (`models/revisions.json` keyed by repo, versus `models/sources.json` restructured to
> `name → {repo, revision}`). Their branch also pinned the ffmpeg archive, which `main` had
> deferred and named as an open gap. Nothing has been reverted in either direction; whoever
> merges has to pick one structure deliberately, because a naive merge leaves `models.py`
> reading a file the fetcher no longer writes. **The decision this entry still needs is
> unchanged in substance and sharper in form:** not "who owns the tree" any more, but who
> merges the branch and which of the two supply-chain implementations survives.
>
> One thing in its favour: the duplicate is what caught a real error. D-073 had refused to pin
> the gated pyannote repo on the grounds that its contents were unseen; their branch pinned it,
> which prompted a re-measurement showing gating covers downloads and not metadata
> (`model_info` and `list_repo_files` succeed with no token; `hf_hub_download` raises
> `GatedRepoError`). Corrected in D-075.


**Needs:** Hawa, one decision — which session owns this working tree, and whether work lands on
`main` or on a branch. No code, no credentials, no hardware.

This is not a complaint about speed. It is that the record has stopped being reliable, which is the
one thing this project's process exists to protect.

### Measured, on 2026-08-08 between 16:00 and 17:10

| Fact | Value |
|---|---|
| Sessions editing this repository | 2 (this one; "Ponytail audit", `local_723777a0`) |
| Files modified in the shared tree at one point | 68 |
| Gate results in three consecutive runs, all from one session's in-flight edits | 23 failed, then 5 failed, then 3 lint errors |
| Branch at the start of the afternoon | `main` |
| Branch now | `codex/production-pipeline-hardening`, 2 commits ahead of `main` |
| `main` vs `origin/main` | ahead by 14, unpushed |

### Four concrete losses, each verifiable in the log

1. **I committed a reversal of a recorded decision without reading it.** `3c270f7` carries
   `survivor_count = min(keep, len(reranked))` — the alternative D-037 clause 4 considered and
   rejected — because I ran `git add src/hawedit/visual_index.py` to land a rate bound and the file
   on disk held someone else's edit too. `git add <file>` stages the file, not the change. Recorded
   as D-066 and restored.

2. **The other session committed my work under its message.** `4e0a80b` ("feat: compose and harden
   the production pipeline") contains my survivor-floor restore, my `PROGRESS.md` amendment and my
   D-066 entry. `9d1292d` ("docs: record survivor floor mutation audit") contains my evidence file.
   Neither message is wrong; neither describes what the commit actually holds.

3. **The same work was done twice, twice.** Both sessions independently wrote a TimeLens2 adapter
   (mine landed as `video_grounding.py`; theirs was backed out of `timelens.py` after Hawa's
   instruction), and both independently derived the 2 fps sampling ceiling from the same measurement
   inside the same hour — recorded as their D-063 and my D-065.

4. **I reset the shared git index while it held their staged work.** `git reset` to keep my own
   commit from carrying their files unstaged theirs. Nothing was lost — a mixed reset leaves the
   working tree alone — but two sessions cannot share one index safely, and I should not have needed
   to touch it.

### Why this is BLOCKED rather than something to engineer around

The project's DONE rule is "code + test + gate green + evidence", and its commit convention is one
unit per commit with the measurement in the message. Both now fail for a reason no guard can catch:
a commit's contents are decided by whatever is on disk when it is written, and two writers means
neither message is trustworthy. `tests/test_claims.py` can check that a claim matches the code; it
cannot check that a commit message matches its diff.

**Any one of these resolves it:**

1. **One session at a time in this checkout.** Simplest, and costs nothing but wall-clock.
2. **A worktree each** — `git worktree add ../hawedit-b <branch>` gives the second session its own
   index and working tree on the same repository. This is what I used to prove M6.3 while the shared
   tree was red, and it worked.
3. **Say which session continues, and stop the other.** Either is capable of the remaining work; the
   duplication above is the cost of not choosing.

**Also needed, and smaller:** the branch. Work moved from `main` to
`codex/production-pipeline-hardening` with no recorded decision, and `main` is 14 commits ahead of
`origin/main`, unpushed. The recorded preference in this session's notes is "commit to main, split by
unit". Confirm whether that still holds.

Until this is answered the loop keeps running and the gate stays green — 1067 passed, 0 skipped as of
`9d1292d` — but a commit here no longer tells you who did what, and neither session can fix that from
inside the checkout.


---

## #13 · §4.1's fifth collision has no defined target form

**Needs:** Hawa, two answers. No code, no credentials, no hardware.

§4.1's collision table has five rows. Four are handled. The fifth —
`| Diacritics ř / ł | Normalize in Latin-script material. |` (`BLUEPRINT.md:232`) — is
unimplemented, and M0.3 claimed all five were done by counting the single Numerals row twice and
calling conjunctive `و` "the fifth". `و` is row four. Demoted to PARTIAL, D-076.

### Measured 2026-08-09 on hawapc01

```
normalize_sorani('řoj baş')  -> 'řoj baş'   changed=False
normalize_sorani('łe gułan') -> 'łe gułan'  changed=False
grep -rlniE "ř|ł" --include=*.py src/ tests/  ->  no files
tests/test_normalize.py SECTION_4_1_COLLISIONS  ->  4 entries, no ř/ł case
```

### Why this is not a code task

**1. What do `ř` and `ł` normalize to?** §4.1 says "Normalize" and does not say to what. In
Kurdish Latin orthography `ř` is a trilled r and `ł` a velarized l — *distinct phonemes*, not
decorated variants. Folding them to `r`/`l` throws away a phonemic distinction that a Kurdish
reader can hear; folding them to anything else is invented. The standing rule is to refuse and
record rather than guess a rule, so nothing was implemented.

**2. Is Latin-script Kurdish in scope at all?** §7's canonical ASR emits `ckb_Arab`, every
Kurdish invariant is written about Arabic-script Sorani, and the caption stack is built on
libass RTL shaping. If Latin-script material never enters this pipeline, the honest resolution is
a recorded scope exclusion in `DECISIONS.md`, not a normalizer nobody calls. If it does — a
transliterated feed, a Kurmanji source — then it needs a defined target form and test cases in
real material.

Either answer closes this. Guessing at the first without the second is how a normalizer that
silently destroys a phonemic contrast ends up in a Kurdish pipeline.

---

## #14 · §4.2's VAD-pause segmentation is dead code, and the correct rule needs real audio

**Needs:** Hawa, or `BLOCKED.md` #1's labelled Sorani audio. No credentials, no hardware.

§4.2 requires sentence segmentation on **"Kurdish punctuation plus VAD pauses"**. The punctuation
half works. The VAD half has never fired, and cannot.

### Measured 2026-08-09 on hawapc01

`pause_follows` (`src/hawedit/sentences.py:104-107`) reaches its VAD branch only when the word gap
is *below* `pause_ms`. That branch then requires a silence **contained** in
`[earlier.end_ms, later.start_ms]` whose own length is **at least** `pause_ms` — which forces the
gap to be at least `pause_ms`. Both conditions cannot hold. Brute-forced to be sure:

```
gap = 100 ms, pause_ms = 400
  no vad pauses            -> 1 sentence
  vad silence 1000..1400   -> 1        (400 ms, starting exactly at the first word's end)
  vad silence  900..1500   -> 1        (spans the gap generously)
  vad silence    0..2000   -> 1        (spans both words)

brute force over 3,528 candidate silences: splits caused = 0
```

The runner computes these silences from Stage 0's real Silero output (`_pauses_between`) and passes
them to `segment_sentences`, where they have no effect — computed and discarded, the same shape as
D-070's `natural_silence_ms`.

### Why this is not a code task

The containment test is clearly wrong, and what should replace it is a decision about Kurdish
speech, not a refactor. Two candidates, both defensible, with opposite failure modes:

1. **Overlap** — a qualifying silence that overlaps `[earlier.end_ms, later.start_ms]` at all ends
   the sentence. Catches the real case this exists for: CTC alignment stretches a word across
   silence, so the word timings show a small gap while VAD saw 400 ms of quiet. Risks
   over-splitting when a long silence merely clips the boundary by a millisecond.
2. **Containment of the boundary point** — the silence must span from before `earlier.end_ms` to
   after `later.start_ms`. Conservative, and only fires when VAD and the alignment genuinely
   disagree about where speech stopped.

Choosing between them changes where Kurdish sentences end, which changes §5's anchors, every
boundary, and every rendered clip. There is no labelled Sorani audio here to measure which
produces better sentence boundaries, and picking by taste is exactly what the "never guess a
threshold" rule exists to prevent. §4.2 does not say.

Until it is answered, `tests/test_sentences.py::test_vad_pauses_currently_cannot_split_a_sentence`
pins the defect so the dead branch cannot be mistaken for a working feature. That test going red
means the fix has landed; delete it then and re-status M1.2.

---

## #15 · How much overlap makes TimeLens evidence "about the clip"?

**Needs:** Hawa, or `BLOCKED.md` #1's labelled Sorani footage. No credentials, no hardware.

M6.1's row says intervals are fused *"only where they are about the clip"*. Measured, **one
millisecond of overlap qualifies**, and §3's `final_out = latest of { …, timelens_interval_end }`
then extends the clip to wherever that interval ends.

### Measured 2026-08-09 on hawapc01

Library level:

```
anchor      : 10000..14000 ms  (a 4.0s sentence)
evidence    : 13999..305000 ms 'applause five minutes later'
overlap     : 1 ms
relevance gate -> ACCEPTED
fused clip  : 10000..305000 ms = 295.0s  extended by 'timelens_interval_end'
```

Through the real `run_pipeline` on the fixture, asserted on the shipped clip:

```
CLIP SHIPPED: 0..4100 ms = 4.10s   (anchor 100..1700 = 1.60s, 2.56x longer)
  extended by 'timelens_interval_end' on 1 ms of overlap
```

The runner's uncaptioned-speech guard **does** catch this when unselected *words* fall in the
swallowed span — verified: a second sentence at 2000 ms produces
`soft boundary expansion 0..4100 ms would include unselected speech beginning with 'لە'`. It cannot
catch the case the feature is most likely to hit: applause, music, silence and untranscribed tails
contain no words, which is exactly what "applause five minutes later" means.

### Why this is not a code task

Bounding the overlap requires a number, and §3 does not give one. It bounds the shot-cut signal
explicitly — *"following shot_cut within 400 ms"* — and says nothing of the kind for
`timelens_interval_end`. Three defensible rules, with different failure modes:

1. **A minimum overlap fraction of the anchor** (say the interval must cover half the anchored
   sentence). Rejects the applause case; also rejects a genuine reaction shot that begins just as
   the sentence ends, which is the commonest real case Stage 5 exists to catch.
2. **A maximum extension window**, like the shot cut's 400 ms. Symmetric with §3's only stated
   window, but TimeLens exists precisely to find ends *beyond* a 400 ms neighbourhood, so this may
   neuter the stage.
3. **A cap relative to the anchored sentence's own length** (e.g. the clip may not exceed some
   multiple of the anchor). Scales with content instead of fixing a constant, and needs the
   multiple chosen.

Each is a threshold, and §8.2 calls misleading output the error class that matters most for a media
organisation — so choosing one by taste is the failure this project's "never guess a threshold" rule
exists to prevent. Real footage would settle it: the question is empirical, not stylistic.

Until it is answered,
`tests/test_timelens.py::test_one_millisecond_of_overlap_currently_qualifies_as_relevant` pins the
measurement so the relevance gate cannot be read as bounding how far evidence may reach. That test
going red means the fix landed — re-status M6.1, close this entry, delete the test.

## #16 · The validator's weights are here and its loader is not

**Measured 2026-08-09 on hawapc01.** `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` — §3 Stage 1's validator,
Apache 2.0 per §7 — is downloaded in full: `model.safetensors` is 4,076,191,640 bytes, 10.1 GB with the
rest of the checkpoint. The machine is capable: torch 2.13.0+cu130, CUDA available, 2 devices,
transformers 4.57.6 and accelerate installed.

It still cannot be loaded:

```
config.json  architectures: ['Qwen3ASRForConditionalGeneration']   model_type: qwen3_asr
transformers.Qwen3ASRForConditionalGeneration   : NO
transformers.models.qwen3_asr                   : ModuleNotFoundError
AutoModel can map 'qwen3_asr'                   : False
```

`config.json` names `transformers_version: 4.57.6`, the version installed, and that version has no
`qwen3_asr` module. The checkpoint's own model card gives the loader:
`from qwen_asr import Qwen3ASRModel  # pip install qwen-asr`.

**What is needed, and why it is not mine to do.** One package. It was not installed because:

1. **A licence.** D-002 admits no dependency without one. §7 records the *model* as Apache 2.0; the
   `qwen-asr` package is a separate artifact and I have not read its licence. "Never guess a licence."
2. **A pin and a checksum.** The supply chain is pinned; adding a runtime dependency outside that is
   the thing `models/revisions.json` exists to prevent.
3. **CI installs `.[dev,media]`.** A locally-installed loader would make the local gate and the gate of
   record disagree about which program they are testing — the failure D-092 and D-093 were about.

So this is Hawa's call, and it belongs in a decision with the licence quoted.

**What it blocks.** M1.4's shortfall as written ("what is missing is the composition, not the
download") was wrong: the composition cannot be written against a loader that is not there, and
writing it anyway would produce an adapter provable only against a stub — which is what D-097 had just
finished measuring the cost of. M0.11's rzgar adapter waits on the same package.

**What it does not block.** Nothing else. The escalation *policy* (`select_for_validation`, D-015) is
implemented and tested; it simply has no consumer yet, and `python -m hawedit.models` now says so
honestly — 9/15 rather than 10/15, with the reason in the detail line (D-099).

## #17 · §3's 64-frame window does not fit the reader on the machine §6 names

**Measured 2026-08-09 on hawapc01** (RTX 3090 Ti, 23.99 GiB; `MCG-NJU/VideoChat3-4B` weights 8.68 GiB).
The largest window the reader can process is **8 frames** at a 21.57 GiB peak — 90 % of the card. Nine
frames OOMs. §3 Stage 2 plans up to `MAX_FRAMES_PER_WINDOW = 64`.

The demand is quadratic in frames (48 -> 196.44 GiB requested, 32 -> 87.31, 24 -> 49.11, 16 -> 21.83,
12 -> 12.28), so this is a factor-of-64 gap, not a margin. Full table and method in
`evidence/largest-window-a-3090ti-can-read.md`; reasoning in D-106.

**Why this is a decision and not a patch.** The three obvious moves are all refused:

1. Lower `MAX_FRAMES_PER_WINDOW`. It is §3's number and BLUEPRINT is frozen; lowering a ceiling to
   make a run pass is what the hard rules forbid.
2. Truncate a 64-frame window to 8 at read time. D-104's guard exists to stop exactly this: an
   embedding of some of the frames describes less footage than the window claims.
3. Sub-segment inside the reader. Combining SV6D readings across chunks means inventing a description
   of a scene from pieces, and it silently changes what a window means to retrieval.

**What is needed from Hawa.** One of:

* **Plan smaller windows** — pass the reader's capacity into `plan_scene_windows`, so hawapc01 uses
  4-second windows instead of up to 32-second ones. This is implementable today and is the route the
  next iteration will take unless told otherwise. It changes Stage 2's retrieval unit: several times
  as many windows, each seeing less context, and §8.2's Recall@K numbers are then measured on a
  different unit than the one §3 describes.
* **Different hardware** for the video phase. The gap closes at roughly 40 GiB for 16 frames and would
  need on the order of 350 GiB for §3's full 64.
* **A different Path B checkpoint** whose attention cost is not quadratic in the window — which is a
  §7 change, and §7 is frozen.

Stage 2's frame extraction, indexing, retrieval and reranking all run: the 38-minute file produced
**164** windows and reached the reader. Only the read step is blocked.

**Resolved for the implementable option, 2026-08-09 (D-108).** `plan_scene_windows` now takes
`max_frames`, exposed as `--visual-max-frames`, defaulting to §3's ceiling and only lowerable. With
`--visual-max-frames 8` the real 38-minute run's visual stage **ran**: 641 windows indexed, 50
retrieved, 7 survivors, 7 candidates, both GPUs at 17,881 MiB, no OOM. The cost is recorded rather than
hidden — 73 windows become 579, each seeing an eighth of the context, so §8.2's Recall@K is measured on
a different retrieval unit than §3 describes. This entry stays open for the part that is **not** mine:
whether HawEdit should ship with §3's window on different hardware, or accept the smaller unit as the
product's real behaviour. That is Hawa's call, and the numbers to make it are above.

### Refreshed 2026-08-09 — what the 8-frame unit costs, measured end to end

The first composed run to finish on the real 38-minute file (D-119's evidence) puts a number on the
consequence this entry is about:

| Fact | Value |
|---|---|
| Windows planned and indexed at `--visual-max-frames 8` | **641** |
| Survivors kept | 7 (§3's 5–10) |
| Candidate window length | **3.38 – 3.88 s** |
| §3's own unit at 64 frames | ~32 s |
| Complete sentences in the media | 185, median **6.56 s**, range 0.41–102.52 s |
| Complete sentences lying wholly inside any of the 5 candidates | **0** |
| Sentences short enough for a 3.38 s window at all | 54 of 185 |

So `--auto-select` had nothing to anchor and produced no selection. It is not arithmetically
impossible — a third of the sentences would fit inside a window that length — but at this unit the
visual path routinely proposes footage no complete Kurdish sentence sits inside, and §5's anchors are
sentence-hard. Choosing the retrieval unit is still yours: §3 fixes 64 frames, this card reads 8
(D-106), and the two cannot both hold.

## #18 · What queries the §2 text index?

**Raised 2026-08-10 (D-134, adversarial pass #19). Needs Hawa.**

`Bm25Index.search` has no caller in `src/`. Measured:

```
$ grep -rn "\.search(" src/
src/hawedit/clip.py:102:            if not _TIMESTAMP.search(label):   # a regex, not the index
```

The runner builds the index (186 documents on the real 38-minute file, 37 distinct idf values),
emits `document_count`, `ngram_size` and `ngram_weight` in the report, and never retrieves from it.

**Two parts of the frozen blueprint disagree about why it exists.**

* §3 Stage 3 Path A: *"Send the **full normalized Sorani transcript** to the Kurdish judge in one
  pass. Not a filtered subset. … If the visual stage filters first, the best clip in the episode is
  gone before anything that understands Kurdish ever reads it."* Under this reading the text index
  is deliberately **not** a pre-filter, and nothing in Stage 3 should query it.
* §9's M2 row: *"Vertical slice: transcript → **BM25** → Gemini → manual boundary → one rendered
  clip"*. Under this reading BM25 is on the path to the judge.

**What the answer changes.** §8.2 measures Recall@K **per discovery path**. If there is a text
retrieval path, it needs a K, a query source and a labelled set to measure against (#1). If there
is not, then §2's text half is a tool for something outside Stage 3 — repurposing search, an
operator query, §7 — and its Recall@K column does not exist.

**Not guessed here.** Inventing a query would put a number in §8.2's per-path table that no design
decision stands behind, and D-117 already showed what happens when a query source is chosen by
convenience: the whole transcript became the query and Stage 2 asked for 40.89 GiB.

**What is done in the meantime:** the index is built in the only shape that can retrieve
(`from_sentences`, D-134), so whichever way this is answered, the structure is ready and the report
says how many documents it holds.

## #19 · CTC-3B's greedy decode is unconditioned, and §3's disagreement trigger compares it to a Kurdish-conditioned decode

**Raised 2026-08-10 (D-135). Needs Hawa.**

§3 Stage 1 routes "any segment where LLM-7B and CTC-3B disagree materially" to the validator.
D-135 gave that trigger its missing input — CTC-3B's own greedy decode of the posteriors Stage 1
already computes. Measured on the real 38-minute file (`ZAR38MinTest.mp4`, 545 segments, 1,547 s on
two 3090 Ti), 542 segments produced a hypothesis, and:

```
first script of each CTC hypothesis, over 542
  ARABIC        428  ( 79.0%)
  LATIN          96  ( 17.7%)
  CJK            11  (  2.0%)
  MALAYALAM 2 · HEBREW 2 · CYRILLIC 1 · DEVANAGARI 1 · BENGALI 1

LLM: کاکە بیلال                       CTC: കക بില                     CER 0.800
LLM: باسی گیم وڵکنیوزم بۆ بکەی        CTC: paseki molknusen bopka     CER 0.960
```

The LLM pass runs with `lang=["ckb_Arab"]`. A greedy argmax over the acoustic model's full
multilingual vocabulary is conditioned on nothing. So `normalized_cer(llm, ctc)` partly measures
**script mismatch** rather than transcription disagreement — and it does so at the decisive margin:

```
normalized CER over all 542 hypotheses            median 0.167   ABOVE  D-015's 0.15 bar
restricted to Arabic-script hypotheses (428)      median 0.125   BELOW  it
escalated on the real run                         312 / 545 = 57%
  disagreement only 176 · both 116 · quartile only 20
```

The quartile alone is 25% by construction. 57% of an episode going to a 4 GiB validator is a
capacity decision, and 176 of those escalations rest on a comparison whose meaning is unestablished.

**Three options, none of them this loop's to take.**

1. **Condition the CTC decode** the way the LLM pass is conditioned. Closest to §3's intent — "two
   models reading the same audio" — but it changes what CTC-3B contributes and its effect on §8.1's
   CER and RTF columns is unmeasured.
2. **Restrict the decode to a Kurdish token subset.** Requires naming which of ~32,000 vocabulary
   entries are Kurdish, which is a guess, and it re-creates the compaction problem D-135 rejected:
   a decode confined to a chosen subset cannot disagree in the way the trigger is for.
3. **Raise the disagreement threshold** until the confound stops firing. A number chosen to make an
   output look right, which D-015 explicitly did not do.

**What is done in the meantime:** the hypotheses are computed and carried in
`transcript.raw.json`'s `segment_confidence` (real data, honestly labelled), §3's rule is applied as
written with D-015's threshold, and the report carries `escalation.by_trigger` so the total can never
be read as validated routing. Nothing is routed anywhere — the rzgar validator's loader is #16.

**The measurement to repeat once this is answered:** the same run, and the fraction of 545 segments
escalating on disagreement alone. It is **176** today.

---

## #20 · The live check needs a video of the built-in sample, and none exists

**What is blocked:** `python -m hawedit.smoke`, the only command in this project that spends money,
cannot be run as shipped.

**Why.** §3 Stage 4 judges real source pixels — `smoke.py` refuses text-only visual judging, and
`AUDIT_REPORT.md` records that refusal as deliberate. So the check needs `--video`. The built-in
Sorani sample spans **0..13,000 ms** (22 words). The only Kurdish video in the repository,
`tests/fixtures/kurdish-speech-3cuts.mp4`, is **4.162 s** and is a different recording. Measured on
hawapc01 with ffmpeg 8.1.1-full, extracting judge keyframes from that fixture:

```
(0, 4000)     20 frames, timestamps 100, 300, 500, 700, 900, 1100 …
(0, 13000)    20 frames, timestamps 325, 975, 1625, 2275, 2925, 3575 …   <- from a 4.16 s file
(5000, 13000) KeyframeError: ffmpeg failed to extract judge keyframes
```

So a shorter video either fails outright, or returns frames stamped across a span the file does not
contain — pixels labelled with times they did not come from, handed to the judge as evidence.

**What would resolve it — Hawa's, because it is a recording, not a decision:** a video of the
built-in sample being spoken, at least 13 s long, committed or pointed at. Then
`python -m hawedit.smoke --video <that file>` is runnable and the README's claim is true without a
caveat.

**Rejected here, and why they are not mine to take:**

1. **Re-cut the sample to match the 4.162 s fixture.** That changes what the live check measures —
   the sample is 22 words of coherent Sorani chosen so a real failure reads as a model problem, and
   trimming it to fit a different recording makes the two agree by construction rather than by
   being the same material.
2. **Ship a synthetic video.** A generated file is not the sample being spoken, and §3 Stage 4's
   whole point is that the judge sees the actual pixels. `AGENTS.md` forbids the stub either way.
3. **Let `--video` be optional again.** That is the defect D-152 fixed: the run spent money on both
   Path A calls and then refused.

**What is done in the meantime:** the refusal is hoisted ahead of every billed call, so the
documented invocation costs nothing when it cannot finish, and the README states the requirement and
this entry rather than promising a check that cannot run.
