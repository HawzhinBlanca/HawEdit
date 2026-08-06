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

## #5 · ffmpeg with libass + HarfBuzz + FriBidi — blocks M3, not M0

Not installed here. §4.3 requires `shaping=complex` **and** a libass actually built with
HarfBuzz — the blueprint is explicit that a build accepting the option may still lack the
backing library, which is why §4.3.6 mandates a golden-file render test in CI rather than
trusting the flag.

Recording it now so M3 does not discover it late. Unblocking this is likely just an install
in the render image, but the golden reference PNG must be generated on a build whose libass
is verified — so the first reference has to come from a trusted box, not from whatever
ffmpeg a CI runner happens to ship.
