# Stage 1 was re-run every time, and the refusal came after the spend

> Measured 2026-08-10 on hawapc01 against `953af2c`.

D-132 made Stage 0 re-runnable. Stage 1 is the expensive stage: **1,547 s** for 545 segments on two
3090 Ti (D-135). `run_pipeline` called `asr.transcribe(...)` before it consulted `TranscriptStore`.

## Before, with a counting producer

```
the real run's canonical transcript: 6,104 words, 545 scored segments

first run into an empty work directory:
  asr.transcribe calls: 1
  transcript.raw.json on disk: True

second run into the SAME work directory, transcript already stored:
  asr.transcribe calls (cumulative): 2
  -> Stage 1 was re-run with a complete transcript on disk: True

and if the second run's ASR returns anything different:
  RawTranscriptImmutable: …\probe.transcript.raw.json already contains a different canonical …
  the refusal arrived AFTER 1 full transcription(s)
```

The second half is the sharper one. Greedy GPU decoding is not bit-reproducible in general, so a
re-run into a used work directory can spend 1,547 s and *then* be refused. **D-071's shape** — an
overwrite refusal after a billed Gemini call — one stage over.

## After

```
first run into an empty work directory:
  asr.transcribe calls: 1
second run into the SAME work directory:
  asr.transcribe calls (cumulative): 1
  -> Stage 1 was re-run with a complete transcript on disk: False
```

## On the real 38-minute file

Two `--omni-asr` runs over one work directory, Stage 0 already cached:

```
FIRST  exit=1 elapsed=1531s bytes=1070737
SECOND exit=1 elapsed=54s   bytes=1070737

first.json  sha256 0bf3b7da4bf84f61  1,070,737 bytes
second.json sha256 0bf3b7da4bf84f61  1,070,737 bytes
byte-identical: True
words: 6104 | index docs: 186 | escalated: 312 of 545
by_trigger: {"quartile_only": 20, "disagreement_only": 176, "both": 116}
```

**1,531 s → 54 s, and the two reports are the same bytes.** The sidecar the first run wrote, and
the audio digest recomputed independently:

```json
{
  "audio_sha256": "312fe70941e143ef831b763ff9b050cbe2fa5b57023a825f63917e9e12e51b0a",
  "producer": "hawedit.asr.WslOmniAsrProducer"
}
```
```
$ sha256 of stage0/audio.wav
312fe70941e143ef831b763ff9b050cbe2fa5b57023a825f63917e9e12e51b0a
```

## Verified on two keys, never assumed

* **audio digest** — same media_id over a different recording re-transcribes rather than shipping
  another video's words;
* **producer** — `asr.py`'s own rule is that a run driven by a test double "can never be read as a
  run on real weights", and keyed on audio alone a stub's transcript would be reused by a real
  `--omni-asr` run.

Absent sidecar, either key wrong, or a failed integrity check all decline. A supplied
`--transcript` writes no sidecar at all, because words handed in were not produced from this audio
here and must never be re-presented as canonical ASR output.

## The stale request file, and the second blocker the test found

Reproduced on the real file last iteration: a run killed mid-transcription left
`stage1/omni-asr-request.json`, and the next attempt died in **78 s** on

```
✗ [Errno 17] File exists: '…\it62asr\stage1\omni-asr-request.json'
```

Stage 0 re-verified, nothing to show, and no instruction in the message. An identical request is
now a resumed run; a different one is refused by name.

**Writing the test for that surfaced a second blocker.** The worker's own
`omni-asr-worker-output.json` is exclusive-create too:

```
E  FileExistsError: [Errno 17] File exists: '…\stage1\omni-asr-worker-output.json'
```

So a killed run left *two* files and the next attempt tripped on whichever came first. A finished
output beside an identical request is this run's answer, so it is resumed — verified by media_id,
with a truncated or foreign one deleted and the worker re-run.

## Proof

```
baseline green: True

RED  the runner transcribes before consulting the store again (the defect: 1,547 s redone)
RED  reuse keyed on the transcript existing, not on the audio it was made from
RED  the audio digest is not compared, so another recording's words are served
RED  the producer is not compared, so a stub's transcript is reused by a real run
RED  an absent provenance sidecar counts as a match
RED  reuse skips the transcript's own integrity check
RED  a supplied --transcript writes a provenance sidecar it did not earn
RED  a stale request file blocks the next run again (the bare FileExistsError)
RED  a request describing different segments is silently reused
RED  a finished worker output is thrown away instead of resumed
RED  a foreign or truncated worker output is trusted

11/11
restored and green: True
```

**The first pass was 10/11.** The survivor was the foreign-output check: dropping the media_id
comparison left every suite green, because no test had ever put another episode's output in the way.
The control now does, and requires the returned transcript to be this run's.

Gate: `VERIFY OK — hawedit gate green`, 1368 tests.
