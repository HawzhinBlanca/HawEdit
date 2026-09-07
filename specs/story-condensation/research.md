# Research: Multi-Part Story Condensation, Semantic Pruning & Automated Sanity Gate

> **Target:** Transform sprawling, rambling long-form Kurdish speech (2–5 minutes) into concise, high-retention 45–60s pro social shorts with automated story summarization, intelligent non-contiguous sentence pruning, frame-locked viral subtitles, smooth audio crossfading, and an automated multi-dimensional sanity gate that detects and reports any failure instantly.

---

## 1. Problem Definition & Gap Analysis

### 1.1 The Limitation of Single Contiguous Spans
In HawEdit's original design (`BLUEPRINT.md` §3 Stage 5), video repurposing was constrained to a single contiguous time interval:
$$\text{Clip} = [t_{\text{in}}, t_{\text{out}}] \quad (\le 60\text{s})$$

When applied to conversational podcasts and interviews (e.g. ZarPodcast, Rudaw, Kurdistan24), this causes severe editorial failures:
1. **The Rambling Dilemma**: A guest takes 30 seconds of discursive background preamble, 40 seconds to recount an anecdote, and 30 seconds to explain the punchline. A single 60s window either cuts off before the punchline (leaving an unresolved story) or starts after the setup (leaving the audience confused).
2. **Filler & Repetition**: Speakers frequently repeat phrases, hesitate, or include minor parenthetical digressions that add zero value to the core narrative.
3. **Dead Framing & Monotony**: Contiguous single-camera tracking becomes visually static over 60 seconds without multi-camera switching or dynamic angle changes.

### 1.2 What the User Explicitly Demands
1. **Stories & Summaries**: The model must detect self-contained stories, define their narrative structure, and generate a clear headline and summary of what the speaker is saying.
2. **Semantic Pruning ("remove words that is not very important for same meaning, not one part")**: Condense the story from multiple non-contiguous parts into a punchy short, extracting the core sentences while discarding tangents and filler.
3. **Automated Sanity Gate ("always check to have something where we know if something didn't work")**: Implement automated quality verification so we never deliver broken output (dead frames, misaligned subtitles, audio clipping, broken grammar) without an immediate fail-stop alert.
4. **Pro Benchmarking**: Follow the exact architectural blueprints of industry leaders (Opus Clip, Descript, Klap, Munch).

---

## 2. Industry Benchmark: How Pro Models & Systems Achieve This

### 2.1 Opus Clip: The Story Arc & Multi-Part Extraction Model
Opus Clip (`opus.pro`) dominates AI podcast clipping by replacing simple duration slicing with **Narrative Arc Mining**:
1. **Macro Segmentation**: Rather than searching for a 60s window, it scans the entire conversation to identify complete narrative units (2–4 minute stories).
2. **Story Decomposition**:
   - **Hook (0–3s)**: High-curiosity statement or question that halts scrolling.
   - **Conflict / Body**: The core obstacle, event, or revelation.
   - **Climax / Payoff**: The conclusion, lesson, or emotional peak.
3. **Headline & Summary Generation**: Automatically generates a localized title for the upper-third cover banner and a 1–2 sentence summary explaining the core message.
4. **AI Cutaways**: Inserts B-roll or dynamic zooms at semantic transition points.

### 2.2 Descript: Semantic Text-Based Speech Pruning
Descript (`descript.com`) revolutionized video editing with **"Remove Retakes & Rambles"**:
1. **Transcript-Level Pruning**:
   - Classifies each sentence and clause into:
     - `CORE_STORY`: Essential plot points and key factual/emotional statements.
     - `ELABORATION`: Minor descriptive details that can be omitted without changing meaning.
     - `RAMBLE / FILLER`: Discursive tangents, throat clearing, repeated phrasing.
2. **Acoustic Continuity**:
   - Cutting video at sentence boundaries leaves audio room tone intact.
   - Applies a **$30\text{ms}–50\text{ms}$ equal-power audio crossfade** (`acrossfade`) across cuts to prevent clicks, pops, and sudden room-tone dropouts.
3. **Timestamp Re-indexing**:
   - Re-indexes all word timestamps so captions and video remain in 100% sync on the condensed timeline.

### 2.3 Automated Sanity & Quality Verification (The "Fail-Safe Gate")
Professional post-production pipelines never rely on blind AI output. Leading engines run an automated **Pre-Delivery Quality Inspection**:
1. **Face Presence & Crop Sanity**: Sample the cropped 9:16 video at regular intervals and shot transitions. If any shot contains 0 detected faces (empty background crop) $\rightarrow$ **FAIL**.
2. **Subtitle Legibility & Sync Sanity**: Inspect the subtitle file to verify:
   - Font size $\ge 100\text{pt}$ for mobile readability.
   - Character count per line $\le 20$ (no crowded multi-line clutter).
   - Safe margin $\ge 240\text{px}$ from bottom (clear of TikTok/Instagram buttons).
   - Alignment drift between subtitle cues and audio $\le 40\text{ms}$.
3. **Audio Quality Sanity**:
   - EBU R128 loudness measured between $-24\text{ LUFS}$ and $-16\text{ LUFS}$.
   - True Peak $\le -1.0\text{ dBFS}$ (zero digital clipping).
   - Silence detector flags any dead air $> 1.2\text{s}$.
4. **Narrative Integrity Sanity**:
   - Verify story headline and summary are populated and in Kurdish.
   - Verify total condensed duration is within the 30–60s sweet spot.
   - Verify pruning ratio is between 30% and 75% (preventing degenerate empty or unpruned clips).

---

## 3. Linguistic Grounding: Kurdish Sorani Pruning Rules

Pruning Kurdish Sorani requires strict grammatical and morphological awareness:

1. **SOV Sentence Structure**:
   - In Sorani Kurdish, the verb almost always terminates the sentence (Subject-Object-Verb).
   - Pruning words *within* a clause often severs verb agreement or leaves hanging prepositions (`لە`, `بە`, `بۆ`).
   - **Rule**: Pruning must operate at the **sentence and clause boundary level**, anchored to forced alignment word timestamps and punctuation (`؟`, `۔`, `.`, `!`) or VAD pauses ($> 350\text{ms}$).
2. **Dangling Conjunctions Guard**:
   - A cut point must never terminate on a forward-pointing conjunction (وەک، چونکە، بەڵام، کەچی، بۆیە، لەبەر ئەوەی).
   - If a sentence ends with a conjunction due to conversational interruption, the conjunction must be excluded from the cut boundary.
3. **Narrative Meaning Preservation Invariant**:
   - The pruned story must preserve:
     $$\text{Meaning}(\text{CondensedStory}) \equiv \text{CoreMeaning}(\text{OriginalStory})$$
   - All critical named entities (people, places, organizations) and core actions must be retained.

---

## 4. Technical Architecture for HawEdit

### 4.1 Data Models
```python
@dataclass(frozen=True, slots=True)
class StoryBeat:
    beat_kind: BeatKind  # HOOK, SETUP, CONFLICT, CLIMAX, RESOLUTION
    sentence_ids: tuple[str, ...]
    source_in_ms: int
    source_out_ms: int
    importance_score: float  # 0.0 to 1.0
    text_kurdish: str

@dataclass(frozen=True, slots=True)
class StorySummary:
    headline_kurdish: str
    summary_kurdish: str
    core_topic: str
    virality_score: float
    key_entities: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class CondensedStoryPlan:
    story_id: str
    summary: StorySummary
    selected_beats: tuple[StoryBeat, ...]
    pruned_sentence_ids: tuple[str, ...]
    total_source_duration_ms: int
    condensed_duration_ms: int
    prune_ratio: float  # e.g. 0.55 (condensed 55% of original time)
    timeline_segments: tuple[tuple[int, int], ...]  # [(in1, out1), (in2, out2), ...]
```

### 4.2 Automated Sanity Gate (`SanityGate`)
```python
@dataclass(frozen=True, slots=True)
class QualityAuditReport:
    passed: bool
    framing_pass: bool
    subtitles_pass: bool
    audio_pass: bool
    story_pass: bool
    detected_faces_per_shot: dict[str, int]
    audio_lufs: float
    audio_true_peak_dbfs: float
    subtitle_max_chars_per_line: int
    subtitle_font_size_pt: int
    subtitle_margin_v: int
    defect_messages: tuple[str, ...]
```

---

## 5. Summary of Findings

1. **Multi-Part Pruning is Required**: Real human speech requires cutting rambling sentences across 2–4 distinct parts of the story to produce a high-impact 45–60s reel.
2. **Equal-Power Crossfading**: FFmpeg `acrossfade=d=0.04:c1=tri:c2=tri` guarantees artifact-free transitions between cut points.
3. **Automated Sanity Gate is Essential**: Running deterministic checks on face presence, subtitle specs, audio LUFS, and narrative completeness gives us 100% confidence in the output and immediately halts on defects.
