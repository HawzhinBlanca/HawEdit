# Kurdish Video Repurposing System — Developer Blueprint

**Version 1.1 · August 2026 — FROZEN FOR IMPLEMENTATION**
Target language: Central Kurdish / Sorani (`ckb`, Arabic script)
Input: long-form podcasts, interviews, news, social video
Output: validated clip candidates with exact boundaries, Kurdish captions, editing JSON / EDL

> **v1.1 changes from v1.0:** canonical ASR moved to LLM-7B with CTC-3B in parallel · Qwen3.6-35B-A3B removed (does not fit) · VideoChat3-4B promoted · NC-licensed aligner removed · boundary algorithm rewritten (was logically broken) · Gemini judge pinned behind an interface · dual-path candidate discovery · pyannote Community-1 · `shaping=complex` verified.

---

## 0. Read this first

Three things decide whether this system works, and none of them is a model choice:

1. **Sorani text normalization.** Kurdish Arabic script has multiple valid encodings for the same grapheme. Skip normalization and your search index silently fails to match text that looks identical on screen. See §4.1.
2. **Word-level forced alignment.** ASR gives you text, not reliable word timing. Boundaries that don't land on sentence edges produce clips that feel broken regardless of model quality. See §4.2.
3. **RTL caption rendering.** FFmpeg's default shaping engine breaks Arabic-script text. You will not catch it in code review — you will catch it when a client sees the burned-in captions. See §4.3.

Everything else here is standard engineering. These three are where Kurdish systems fail.

---

## 1. Design principles

| Principle | Implication |
|---|---|
| **OmniASR hears Kurdish · Gemini understands Kurdish · local specialists handle pixels, search and timing** | The core separation. Every component slots into exactly one of these three roles. |
| **The raw Sorani transcript is canonical** | Normalized text and English translation are derived artifacts. They never overwrite the source. |
| **Dual-path candidate discovery** | Verbal candidates and visual candidates are found independently, then unioned. Neither path may filter the other. |
| **Every stage emits and consumes JSON** | Stages are independently testable, replaceable, re-runnable. |
| **Fail visible, not silent** | Every stage writes a confidence score. Low confidence routes to human QC, never to silent acceptance. |
| **No model changes without measurement** | After freeze, a component may only be swapped on evidence from §8, not on a leaderboard. |

---

## 2. Architecture

```
┌─ STAGE 0 · INGEST ─────────────────────────────────── CPU (3990X, 64c) ─┐
│  ffmpeg demux → 16 kHz mono WAV + video proxy                            │
│  PySceneDetect · Silero VAD · pyannote Community-1 · keyframes           │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓  VAD segments < 40 s
┌─ STAGE 1 · SPEECH ─────────────────────────── BOTH GPUs, IN PARALLEL ───┐
│  GPU 0: omniASR_LLM_7B_v2   → canonical Sorani transcript                │
│  GPU 1: omniASR_CTC_3B_v2   → confidence + CTC emissions                 │
│         ↳ disagreement / hard spans → rzgar Qwen3-ASR-Sorani (validator) │
│  Viterbi forced alignment on CTC emissions → word timestamps             │
│  KLPT normalization → parallel normalized transcript                     │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─ STAGE 2 · INDEX ──────────────────────────────── GPU 1 + CPU ──────────┐
│  Text:   BM25 + character n-grams over normalized Sorani                 │
│  Visual: Qwen3-VL-Embedding-2B per scene → Qwen3-VL-Reranker-2B          │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─ STAGE 3 · DUAL-PATH CANDIDATE DISCOVERY ───────────────────────────────┐
│                                                                          │
│   PATH A — VERBAL (cloud)          PATH B — VISUAL (local, GPU 0)        │
│   Gemini reads the FULL            VideoChat3-4B over scenes             │
│   Sorani transcript                + embedding/rerank retrieval          │
│   → hooks, stories, arguments      → reactions, gestures, action,        │
│                                       scene changes, non-verbal beats    │
│                    │                            │                        │
│                    └────────── UNION ───────────┘                        │
│                                                                          │
│  NEITHER PATH FILTERS THE OTHER. The strongest Kurdish moment is often   │
│  two people sitting still while someone says something extraordinary.    │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓  top 5–10%
┌─ STAGE 4 · FINAL EDITORIAL JUDGE ───────────────────────── CLOUD ───────┐
│  KURDISH_EDITORIAL_JUDGE ← candidate transcript + keyframes (+ video)    │
│  hook · self-containment · payoff · meaning fidelity ·                   │
│  misleading-edit risk · cultural landing · Kurdish title/description     │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─ STAGE 5 · BOUNDARIES ──────────────────────────── GPU 1 + CPU ─────────┐
│  TimeLens2-4B → visual evidence intervals (NOT cuts)                    │
│  Sentence-hard fusion with word timings, VAD, speaker turns, shot cuts  │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─ STAGE 6 · RENDER ─────────────────────────────────── CPU + NVENC ──────┐
│  crop/reframe · ASS generation · libass burn-in, shaping=complex        │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
                          HUMAN QC GATE (always)
                                    ↓
                 MP4 · SRT/ASS · editing JSON · EDL
```

---

## 3. Stage specifications

### Stage 0 — Ingest

**CPU only. Never blocks a GPU.** Spawn many *single-threaded* ffmpeg processes rather than one with `-threads 64` — the 3990X is Zen 2, modest single-thread speed and enormous parallelism.

```bash
ffmpeg -i "$SRC" -vn -ac 1 -ar 16000 -af loudnorm=I=-23:TP=-2:LRA=7 \
       -c:a pcm_s16le "$WORK/audio.wav"
ffmpeg -i "$SRC" -vf "fps=1,scale=-2:720" -c:v libx264 -crf 28 -an "$WORK/proxy.mp4"
```

- **Shots:** PySceneDetect `ContentDetector`, threshold ~27, tuned per content type.
- **VAD:** Silero, `max_speech_duration_s=38` (margin under OmniASR's 40 s ceiling).
- **Diarization:** `pyannote/speaker-diarization-community-1` on pyannote.audio 4.x. Chosen for **exclusive speaker diarization**, which makes reconciliation with transcript timestamps materially easier — directly relevant to Stage 5. Licence is CC-BY-4.0: commercially usable, attribution required. Ship the attribution notice. Note the repo is gated on Hugging Face — factor the access-acceptance step into deployment automation. Keep `speaker-diarization-3.1` (MIT) as a benchmark control.

### Stage 1 — Speech

**Both GPUs run simultaneously. Different jobs, not a cascade.**

| GPU | Model | VRAM | Role |
|---|---|---|---|
| 0 | `omniASR_LLM_7B_v2` | ~17 GiB | **Canonical Sorani transcript** |
| 1 | `omniASR_CTC_3B_v2` | ~8 GiB | Confidence posteriors + CTC emissions for alignment |
| — | `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` | ~4 GiB | Validator on disagreement / hard spans |

**Why LLM-7B is canonical:** Meta's only published Central Kurdish figure — `ckb_Arab`, 59.6 training hours, **CER 6.0** — belongs to the 7B LLM model. No per-language CER is published for CTC-3B. This is a *provisional* choice pending §8.1; your own benchmark could overturn it.

**Why CTC-3B still runs:** the LLM decoder gives no frame-level posteriors. CTC does, and that's what forced alignment needs. Running it in parallel costs nothing and produces both confidence scores and word timings from the same acoustic family.

**Do not use the `Unlimited` variants by default.** VAD already produces sub-40 s units. Unlimited removes the file-length interface limit but still segments internally at `N=15, M=1` — 15-second windows conditioned on one previous segment. Meta states its CER is on par with the standard LLM models.

> **Throughput:** Meta publishes RTF 0.003 for CTC-3B and 0.092 for LLM-7B. Those figures are measured at **batch=1, 30 s audio, BF16, on an A100**. Do not derive wall-clock promises for hawapc01 from them. Measure on your own hardware in §8.1 and put *that* number in the capacity plan.

**Escalation:** compute mean token log-probability per segment from CTC posteriors. Route the bottom quartile, and any segment where LLM-7B and CTC-3B disagree materially, to the validator. Never escalate on duration or word-count heuristics.

### Stage 2 — Index

**Text:** BM25 + character 3-grams over the normalized transcript. Character n-grams matter more than usual — Sorani is morphologically rich with heavy clitic attachment, so word-level matching misses variants a human reads as identical.

**Visual:** `Qwen3-VL-Embedding-2B`, one embedding per scene. Reference settings run ~1 fps with a maximum of 64 frames, so segment before embedding. Retrieve top 50 → `Qwen3-VL-Reranker-2B` → keep top 5–10.

### Stage 3 — Dual-path candidate discovery

**This is the most important structural decision in the system.**

**Path A — verbal.** Send the **full normalized Sorani transcript** to the Kurdish judge in one pass. Not a filtered subset. A purely verbal moment — no motion, no visual signal — is invisible to every local component in this pipeline. If the visual stage filters first, the best clip in the episode is gone before anything that understands Kurdish ever reads it.

Cost is not a reason to withhold it: a one-hour transcript is roughly 20K tokens, about **$0.04** per source hour.

**Path B — visual.** `VideoChat3-4B` over scenes, plus embedding/rerank retrieval. Finds reactions, gestures, action, scene changes, non-verbal beats.

**Union, never intersect.** Candidates from either path proceed.

> **Governance consequence — read before enabling Path A.** Full-transcript discovery means 100% of every transcript leaves your network, not the 5–10% the earlier design assumed. For COMMS and KAAE material, paid tier and Vertex with zero-data-retention configured become **mandatory, not advisory**. Confirm this before the first client job runs.

> **Cost optimisation.** Path A already scores its candidates. Stage 4 should add *visual* context to survivors, not re-derive verbal judgment. Don't pay the judge twice for the same reasoning.

**VideoChat3-4B notes:** promoted from challenger to provisional production model because Qwen3.6-35B-A3B does not fit (see §7) and VideoChat3 is the strongest specialist that does. It has not proven superiority — make its replacement a config change. Segmentation is mandatory: the authors report ~17.7 GB at 256 frames and ~26.7 GB at 512.

**Prompt schema — SV6D.** Use the six-dimension structure from the Leum-VL paper as your output schema, applied to models you actually run: `subject · aesthetics · camera language · editing · narrative · retention`. Every label must cite a timestamp. Reject output where a claim has no timeline evidence.

### Stage 4 — Final editorial judge

```
KURDISH_EDITORIAL_JUDGE = gemini-2.5-pro     # pinned, today
SHADOW                  = gemini-3.1-pro     # evaluated, not routed
```

**Why 2.5 Pro is pinned:** you have tested evidence that it performs well on your Sorani. You have none for 3.1 Pro, and prior experience that newer Gemini versions are not automatically better on Kurdish. Empirical beats newer.

**Deprecation status (verified against the live Gemini API deprecations page):**

```
| gemini-2.5-pro   | June 17, 2025 | No shutdown date announced |
| gemini-2.5-flash | June 17, 2025 | No shutdown date announced |
```

The October 16, 2026 date applies to **Vertex AI / Agent Platform**, not the Developer API. Treat this as a managed migration with a shadow test, not a deadline. Switch only when 3.1 Pro beats 2.5 Pro on your Sorani regression set.

All routing goes through the `KURDISH_EDITORIAL_JUDGE` interface. Swapping providers must be a config change, never a refactor.

**Judge outputs:** hook strength · self-containment · payoff location · meaning fidelity · misleading-edit risk · cultural landing · Kurdish title, description, hashtags.

**Input modes:**

| Mode | Payload | Tokens/source hour | Cost/source hour |
|---|---|---|---|
| Path A discovery | Full Sorani transcript | ~20K | ~$0.04 |
| Stage 4, transcript-first | Candidate slice + ~20 keyframes | ~20K | ~$0.04 |
| Stage 4, with video | 20 × 60 s segments | ~360K | ~$0.72 (~$0.36 batched) |

Video bills at ~300 tokens/sec at default media resolution, ~100 at low. Keep each request under 200K tokens to stay on the lower Pro price tier. Batch API takes 50% off; cached input reads at 10% of base.

### Stage 5 — Boundary fusion

**TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce editorial cuts and cannot locate a speech-only idea without transcript timing.** Treat its output as one input among five.

```
HARD CONSTRAINT — sentence boundaries from forced alignment
    anchor_in  = start of the first complete selected sentence
    anchor_out = end   of the last  complete selected sentence

SOFT ADJUSTMENT — may only extend OUTWARD
    final_in  = earliest of { anchor_in,  vad_onset − 120 ms,
                              preceding shot_cut within 400 ms,
                              speaker_turn_start }
    final_out = latest   of { anchor_out + 200 ms tail, natural silence,
                              following shot_cut within 400 ms,
                              speaker_turn_end, timelens_interval_end }

INVARIANT (assert before render, reject on failure)
    final_in  <= anchor_in
    final_out >= anchor_out
```

**A clip never starts or ends mid-sentence.** If no sentence boundary exists within tolerance, extend to the next one or reject the candidate. This single invariant accounts for most of the perceived quality gap between an auto-clipper that feels professional and one that feels broken.

### Stage 6 — Render

Reframing, captions, encode. Caption requirements in §4.3 are not optional. Vertical reframing tracks the active speaker from diarization plus face detection; add SAM 3 only if face-centred cropping proves insufficient on real footage.

---

## 4. Kurdish-specific requirements

**This section is the difference between a working system and a demo.**

### 4.1 Sorani text normalization — MANDATORY

Multiple valid Unicode encodings exist for identical-looking graphemes. Without normalization, two identical Kurdish sentences will not match in your index and you will not see why.

| Collision | Detail |
|---|---|
| `ه` + ZWNJ vs `ە` | AsoSoft replaces every `"ه" + ZWNJ` with Kurdish `ە`. Both are everywhere in real text. |
| Farsi vs Arabic `ی` / `ک` | Kurdish uses the Farsi forms; Arabic keyboards emit `ي` and `ك`. |
| Numerals | Farsi (`۰۱۲`), Eastern Arabic (`٠١٢`), Western (`012`) all occur. KLPT `unify_numeral` converts. |
| Conjunctive `و` | Often joined to the previous word; AsoSoft applies a separation algorithm. |
| Diacritics `ř` / `ł` | Normalize in Latin-script material. |

**Tools:** KLPT (`sinaahmadi/klpt`) `preprocess` module — `normalize`, `standardize`, `unify_numerals`; Sorani and Kurmanji, Arabic and Latin scripts, UTF-8 only. AsoSoft corpus rules as reference implementation.

```
transcript.raw.json    ← EXACTLY as ASR emitted. Never modified. Ships to client.
transcript.norm.json   ← KLPT-normalized. Used for BM25, embeddings, model input.
transcript.en.json     ← Auxiliary English. Retrieval and reasoning aid ONLY.
```

If you find yourself editing the raw transcript in place, stop — you've introduced a bug you cannot detect later.

### 4.2 Word-level forced alignment — MANDATORY

**Implement Viterbi forced alignment against OmniASR CTC-3B emissions.** You already run the acoustic model, so there is no second model and no alignment mismatch.

This is a real engineering module with its own tests, not a library call — Meta does not ship timestamp extraction as a finished feature.

> **Do not use `mms-300m-1130-forced-aligner` or the `ctc-forced-aligner` package.** Verified licence: **CC-BY-NC-4.0**. Excluded on the same grounds as vekol-stt.

Sentence segmentation runs on the aligned output using Kurdish punctuation *plus* VAD pauses. ASR punctuation for low-resource languages is unreliable; never rely on it alone.

### 4.3 RTL caption rendering — MANDATORY

FFmpeg's `subtitles` and `ass` filters expose a `shaping` option. Per the official filter documentation:

> `complex` — "Slower shaper using OpenType for substitutions and positioning. **Required for correct rendering of complex scripts such as Arabic, Hebrew, Devanagari and Thai. Requires libass to be built with HarfBuzz.**" The default is `auto`.

**Requirements:**

1. **Set `shaping=complex` explicitly.** Never rely on `auto`.
   ```bash
   ffmpeg -i in.mp4 -vf "ass=captions.ass:shaping=complex:fontsdir=./fonts" ...
   ```
2. **libass must be built with HarfBuzz and FriBidi.** Verify at deploy time — a package that accepts the option may still lack the backing library:
   ```bash
   ffmpeg -hide_banner -buildconf | grep -E "libass|libfribidi|libharfbuzz"
   ldd $(which ffmpeg) | grep -E "harfbuzz|fribidi"
   ```
3. **Use `ass` / `subtitles`, not `drawtext`.** `drawtext` shaping now requires `--enable-libharfbuzz` and its own `text_shaping` flag; the ASS path is the supported route for captions.
4. **Font must cover the full Kurdish set** — `ڕ ڵ ۆ ێ چ ژ پ گ ە`. Missing glyphs render as boxes. Noto Naskh Arabic or Vazirmatn are safe starts. Reference the font via `fontsdir`; do not rely on fontconfig resolution on the render host.
5. **Insert line breaks yourself** from the word alignment. `wrap_unicode` (Unicode Line Breaking, requires libass ≥ 0.17.0 built with libunibreak) is **disabled by default for native ASS** — which is what you generate. Automatic wrapping on RTL text produces bad break points regardless.
6. **Ship a golden-file test.** Render one fixed Kurdish caption at build time, compare against a reference PNG. Shaping regressions arrive silently through ffmpeg or libass updates and are invisible in code review. This is the real safeguard — the option flag is not.

### 4.4 Dialect coverage

Evaluate separately on Hewlêr, Slemani and Mukriyan. A single aggregate CER hides the dialect where the product is actually used. The known weak spot in existing Sorani models is heavy regional dialect and fast conversational speech.

---

## 5. Data contracts

```jsonc
{
  "clip_id": "uuid",
  "media_id": "uuid",
  "in_ms": 84200,
  "out_ms": 112700,
  "discovery_path": "verbal",          // verbal | visual | both

  "boundary": {
    "anchor_in_ms": 84600,             // sentence start — HARD
    "anchor_out_ms": 112400,           // sentence end   — HARD
    "in_extended_by": "vad_onset",
    "out_extended_by": "shot_cut",
    "sentence_complete": true,         // invariant — false ⇒ reject
    "confidence": 0.91
  },

  "transcript": {
    "raw_ckb":  "...",                 // canonical, unmodified
    "norm_ckb": "...",
    "en_aux":   "...",
    "words": [{"w":"...","start_ms":84600,"end_ms":84920,"conf":0.97}],
    "asr": {"canonical":"omniASR_LLM_7B_v2","aligner":"ctc_viterbi",
            "validated_by":null,"mean_logprob":-0.21}
  },

  "speaker": "SPK_01",

  "editorial": {
    "hook_score": 0.88,
    "self_contained": true,
    "meaning_fidelity": 0.94,
    "misleading_edit_risk": 0.03,
    "cultural_landing": 0.86,
    "narrative_role": "payoff",
    "judge": "gemini-2.5-pro",
    "sv6d": { "subject":"...","aesthetics":"...","camera":"...",
              "editing":"...","narrative":"...","retention":"..." }
  },

  "output": {
    "title_ckb": "...", "description_ckb": "...",
    "crop_target": "speaker_face", "caption_style": "word_highlight",
    "durations": [15, 30, 60]
  },

  "qc": { "auto_pass": true, "flags": [], "human_reviewed": false }
}
```

**Rejection is a first-class outcome.** Every rejected candidate keeps a `reject_reason` and its `discovery_path`. That set is your only measure of recall.

---

## 6. Hardware & deployment

**hawapc01** — Threadripper 3990X (64c/128t, 64 PCIe 4.0 lanes), 256 GB RAM, 2× RTX 3090 Ti, NVLink active (4 links × 14.062 GB/s = 112.5 GB/s bidirectional).

```
ASR PHASE        GPU 0 → omniASR_LLM_7B_v2  (~17 GiB)
                 GPU 1 → omniASR_CTC_3B_v2  (~8 GiB)

VIDEO PHASE      GPU 0 → VideoChat3-4B      (segmented)
                 GPU 1 → Embedding / Reranker / TimeLens2  (sequential)

CPU (all phases) ffmpeg · scene detect · VAD · diarization · alignment ·
                 indexing · render — massively parallel, never blocks a GPU

CLOUD            KURDISH_EDITORIAL_JUDGE — full transcript (Path A) +
                 top 5–10% candidates (Stage 4)
```

Load models **sequentially** within a phase; do not hold all of them resident. Verify NVLink is carrying traffic before assuming it:

```bash
nvidia-smi topo -m      # GPU0/GPU1 cell should read NV4
# p2pBandwidthLatencyTest — expect ~50+ GB/s unidirectional; ~20 means PCIe fallback
```

**The 256 GB is load-bearing.** Hold decoded frames, keyframe caches and the transcript index in RAM. On a batch pipeline that often beats any GPU-side optimisation.

**Role split:** hawapc01 runs the pipeline. M4 Max runs orchestration, the editor UI, the transcript DB and development. The 4090 box runs preview, or a third parallel worker during batch runs.

---

## 7. Model registry

| Component | Model | Licence |
|---|---|---|
| Scene detection | PySceneDetect | open |
| VAD | Silero VAD | MIT |
| Diarization | `pyannote/speaker-diarization-community-1` | CC-BY-4.0 (attribution required, gated repo) |
| **Canonical ASR** | `omniASR_LLM_7B_v2` | Apache 2.0 |
| ASR confidence + emissions | `omniASR_CTC_3B_v2` | Apache 2.0 |
| ASR validator | `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` | Apache 2.0 |
| Forced alignment | Custom Viterbi on CTC emissions | in-house |
| Normalization | KLPT | open |
| Visual embedding | `Qwen3-VL-Embedding-2B` | Apache 2.0 |
| Reranking | `Qwen3-VL-Reranker-2B` | Apache 2.0 |
| Local video understanding | `MCG-NJU/VideoChat3-4B` | Apache 2.0 |
| Visual temporal evidence | `MCG-NJU/TimeLens2-4B` | Apache 2.0 |
| Kurdish judge (both stages) | `gemini-2.5-pro`, pinned | commercial |
| Judge shadow | `gemini-3.1-pro` | commercial |
| Captions | ASS + libass/HarfBuzz/FriBidi | LGPL/GPL |

**Excluded, with reasons:**

| Excluded | Reason |
|---|---|
| CLIP as primary retrieval | Frame-averaging loses temporal structure — 0.325 vs 0.75+ NDCG@10 |
| Whisper | OmniASR is stronger for `ckb` |
| Qwen3.6-35B-A3B | GPTQ-Int4 checkpoint is **24.4 GB** of weights — no margin on a 24 GB card |
| `mms-300m-1130-forced-aligner` | **CC-BY-NC-4.0** |
| `RevgeAI/vekol-stt-ckb-small` | **CC-BY-NC-4.0** |
| Leum-VL-8B (the model) | 39 downloads/mo, unchanged since March 2026. The SV6D *schema* is kept; the weights are not |
| Seed2.1 Pro (in v1) | Best published video scores anywhere (89.2 VideoMME, 79.5 TOMATO, 80.7 OVOBench — all above Gemini 3.1 Pro) and an explicit long-movie-to-shorts showcase, but zero Sorani evidence. Benchmark in §8.2; do not add a second cloud dependency on benchmarks alone |
| Gemini YouTube-URL input | No audio track means no OmniASR pass. Triage only, never a pipeline input |
| OmniASR `Unlimited` as default | VAD already yields sub-40 s units; internal `N=15, M=1` segmentation remains |

Every figure above is vendor- or author-reported and not independently replicated.

---

## 8. Evaluation harness

**Build this before Stage 3.** No public benchmark measures Sorani video repurposing. Your annotated set is the only ground truth that exists.

### 8.1 ASR benchmark — blocks everything

Several hours across: **Hewlêr · Slemani · Mukriyan · formal news · casual podcast · Kurdish–English and Kurdish–Arabic code-switching · noisy environments · overlapping speakers · named entities and political terminology.**

Candidates: `LLM_7B_v2` · `CTC_3B_v2` · `LLM_Unlimited_3B_v2` · `rzgar-ckb-v1` · Gemini 2.5 Pro native audio.

Metrics: normalized CER · spacing-free CER · named-entity error · code-switch error · **real-time factor measured on hawapc01** · VRAM · long-audio failure rate · alignment accuracy from CTC emissions.

**Decision rule:** LLM-7B stays canonical unless another model shows a material accuracy gain on *your* audio at acceptable throughput. Published CERs across different models are computed on different datasets with different normalization — they are not comparable. Only this harness produces comparable numbers.

Also run here: pyannote Community-1 vs 3.1 on Kurdish multi-speaker material (DER, plus boundary-reconciliation quality against your word alignment).

### 8.2 Repurposing benchmark

200–500 human-reviewed candidates labelled for: hook strength · independent comprehensibility · factual fidelity · emotional payoff · visual continuity · in-point quality · out-point quality · suitability at 15/30/60/90 s · reject reason · **discovery path that found it**.

Compare: Gemini 2.5 Pro · Gemini 3.1 Pro · VideoChat3-4B · Seed2.1 Pro (optional).

Metrics: candidate Recall@20 **per discovery path** · human pairwise preference · temporal IoU · sentence-completeness rate · **misleading-edit rate** · cost per source hour · wall-clock per source hour.

Misleading-edit rate is the one that matters for a media organisation. An engaging clip that misrepresents the speaker is worse than no clip.

**Per-path recall is what justifies the dual-path cost.** If Path B never surfaces a winner Path A missed, collapse it.

### 8.3 Render regression tests

- Golden-file Kurdish caption render, compared per build
- Font coverage assertion across the full Kurdish character set
- Boundary invariant: assert `final_in <= anchor_in` and `final_out >= anchor_out` on every shipped clip

---

## 9. Build order

| Milestone | Deliverable | Blocks |
|---|---|---|
| **M0** | ASR benchmark harness + labelled Sorani audio set | Everything |
| **M1** | Stage 0 + Stage 1 → raw/normalized transcript with word timings | M2 |
| **M2** | Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip | Proves the concept |
| **M3** | Stage 6 render path with verified RTL captions + golden test | Client delivery |
| **M4** | Stage 3 Path A (full-transcript discovery) | Verbal recall |
| **M5** | Stage 2 visual index + Stage 3 Path B | Visual recall |
| **M6** | Stage 5 TimeLens2 + sentence-hard fusion | Boundary precision |
| **M7** | Repurposing eval set + threshold tuning | Quality gates |
| **M8** | Auto-reframe (SAM 3 / Molmo2) | Vertical formats |

**M2 is the one that matters.** Get one clip out the door through the thinnest possible path. Every stage after that must justify itself by fixing a failure visible in real output.

---

## 10. Known risks

| Risk | Mitigation |
|---|---|
| Sorani CER unmeasured on your dialects | M0. If LLM-7B underperforms, the canonical model changes — plan capacity for both. |
| Published RTF is A100, not 3090 Ti | Measure on hawapc01 in M0. Do not put derived wall-clock figures in the capacity plan. |
| Gemini regresses on Sorani between versions | Pin the version, keep a Sorani regression suite, shadow-test before any switch. |
| Full transcript leaving the network | Paid tier + Vertex ZDR mandatory before the first client job. |
| libass shaping regression | `shaping=complex` explicitly + runtime capability test + golden-file test in CI. |
| Dialect blind spot | Per-dialect metrics, never a single aggregate. |
| VideoChat3 unproven for this task | Config-swappable. Per-path recall in §8.2 decides whether it stays. |
| Vendor deprecation | All cloud calls behind `KURDISH_EDITORIAL_JUDGE`. Provider swap = config change. |
| Attribution obligations | Community-1 (CC-BY-4.0) requires an attribution notice in shipped product docs. |

---

## Appendix — Verification commands

```bash
# RTL stack present
ffmpeg -hide_banner -buildconf | grep -E "libass|libfribidi|libharfbuzz"

# shaping option accepted by this build
ffmpeg -hide_banner -h filter=ass | grep -A6 shaping

# NVLink live, not merely enumerated
nvidia-smi topo -m && nvidia-smi nvlink -s

# OmniASR language code present
python -c "from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs; \
print('ckb_Arab' in supported_langs)"

# Kurdish font coverage
python - <<'PY'
from fontTools.ttLib import TTFont
cmap = TTFont("NotoNaskhArabic-Regular.ttf").getBestCmap()
need = "ڕڵۆێچژپگە"
print([c for c in need if ord(c) not in cmap] or "full coverage")
PY
```

---

**Architecture frozen. Further model changes require measured improvement on your own dataset, not another leaderboard. Next action: M0.**
