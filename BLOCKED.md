# BLOCKED — needs Hawa

The only legitimate reason to stop the loop. Everything here is a hard external dependency:
no amount of engineering in this container resolves it.

Environment this was assessed in: cloud container, no GPU, no ffmpeg, no client media,
no API credentials. Python 3.11, PyPI reachable.

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
3. Authorisation to bootstrap from a public Sorani corpus (e.g. Common Voice `ckb`) as an
   *interim* set. This is read speech: it would exercise the harness end-to-end on genuinely
   real Kurdish audio but would **not** satisfy the podcast / overlapping-speaker / dialect
   split §8.1 asks for, so it cannot close M0 — only de-risk it. Say the word and I will do
   this, and label the report as interim so no threshold is derived from it.

---

## #2 · hawapc01 (or any GPU) — blocks M0.11, M0.13

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

## #6 · The interim corpus is authorised but not reachable — network policy

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

## #7 · The hawedit2 CI job is not a *required* status check

**Needs:** Hawa, in the GitHub repository settings. One click, no code.

`.github/workflows/hawedit2.yml` now runs the gate on a clean runner — audit finding #5 was
that nothing ever did. But a workflow that runs is not a workflow that blocks: until `gate`
is added to the protected branch's required status checks, a red run is a red tick beside a
mergeable PR.

This matters more here than it usually would, because the project's own definition of DONE is
"verify.sh green **AND** required CI checks green". The second half of that sentence currently
refers to nothing.

**To unblock:** Settings → Branches → branch protection rule for the default branch → Require
status checks to pass → add **`gate`** (workflow `hawedit2`).

Until then, treat every DONE mark as resting on a local run plus an advisory CI run.

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
