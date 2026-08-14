# Running the real 38-minute file: two defects, one fixed, one measured

> Measured 2026-08-09 on hawapc01 against `98e61de`.
> Source: `C:\Users\Wareen\Desktop\Test Videos\ZAR38MinTest.mp4` â€” h264 640Ã—360, 25 fps,
> AAC 44.1 kHz stereo, **2313.8 s**, 82,446,418 bytes.

Every previous iteration tested this repo against fixtures. This one ran the CLI on a real
38-minute Kurdish video, with no `--transcript` and no `--verdict` â€” the two flags whose own help
text calls them stand-ins.

## What the pipeline refused, correctly

```
--omni-asr --gemini --visual --timelens --face-reframe --auto-select
    âœ— no Gemini API key. Run `python -m hawedit.credentials` â€¦ exit 2

--omni-asr --visual --timelens --face-reframe --auto-select
    âœ— canonical OmniASR WSL2 runtime is not provisioned. Run hawedit-asr-setup â€¦ exit 2

(stage 0 only)
    every downstream stage reported `skipped` with a named blocker and an empty `clip`
```

No stub, no placeholder, no substituted model. Both refusals named the missing thing and the command
that supplies it. Stage 0 ran for real: `audio.wav` 74,039,412 bytes and `proxy.mp4` 51,124,346 bytes
from the 38-minute source.

## Defect 1 â€” `wsl.exe --` ate the environment (fixed, D-134)

`hawedit-asr-setup` failed with **uv's** error: `a value is required for '[PATH]'`. Measured cause:

```
wsl.exe --      env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc â€¦
    -> RUNTIME=[UNSET]   uv=none   python3.12=none
wsl.exe --exec  env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc â€¦
    -> RUNTIME=[/tmp/x]  uv=~/.local/bin/uv   python3.12=~/.local/bin/python3.12
```

`--` only ends option parsing; the command still goes through the default shell, which expanded the
`$VAR` references before `bash -lc` saw them and used a PATH without `~/.local/bin`. So
`venv="$HAWEDIT_WSL_RUNTIME/venv"` was empty and `uv venv --python 3.12 ""` had no path.

The same three lines existed a second time in `WslOmniAsrProducer._prefix`, also with `--`, and that
call passes `env PYTHONPATH=<source>` to reach `hawedit.asr_worker` â€” so Stage 1 would have died on
an unimportable worker even after a good install. One shared prefix now.

**Proven, not inspected:**

```
OmniASR import OK; CUDA GPUs visible: 2
READY: OmniASR WSL2 runtime at C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr
```

with the pinned `omnilingual-asr==0.2.0`, `klpt==0.1.7`, `fonttools==4.55.3` in a Python 3.12 venv
inside WSL2. This closes M1.4's "the WSL runtime itself is not provisioned here either".

## Then Stage 1 ran, on real Kurdish, and died on one segment out of 547

```
Stage 0 -> 547 speech segments, 2076.5 s of speech in 2313.8 s of media (89.7%)
           shortest: 316, 316, 316, 316, 348, 348, 380, 380, 380, 380, 412, 444 ms
             <250ms  0      250-375  6      375-500  11      500-1000  67      >=1000  463
Stage 1 -> both GPUs loaded, segments transcribed, then:

hawedit.forced_alignment.AlignmentInfeasible: 15 frames cannot emit 15 tokens: CTC needs at
least 17 frames (one per token, plus a blank between each repeated pair). Aligning anyway would
invent timings, and a wrong word boundary becomes a clip that starts mid-word â€¦
```

The guard is right and must stay: M1.1 refuses rather than inventing timings, and invariant #5 says
word timings come from CTC Viterbi or not at all. A 316 ms segment is ~15 frames at these models'
framing, and the model emitted 15 tokens for it â€” more text than the audio can carry, which is
evidence about the *text*, not only the timings.

**What is wrong is the blast radius.** `asr_worker.run_request` transcribes all 547 segments in a
single generator expression with no per-segment failure path, so one unalignable segment discards a
completed 38-minute Stage 0 and ~9 minutes of GPU work, and the operator gets no transcript at all.

This repo already has the answer for the same shape, in `MeasurementSession.measure`:

> A raised exception becomes a recorded failure rather than an aborted run: Â§8.1 wants a long-audio
> failure *rate*, and a run that dies on the first 62-second file produces no rate at all.

**Not fixed in this commit, deliberately.** The honest fix records the per-segment failure and its
reason and continues â€” but a transcript that silently omits a segment is worse than a refusal, so the
count and reasons have to reach the artifact, and `RawTranscript` is Kurdish invariant #1's
write-once canonical file that ships to the client. Changing what it carries is a schema decision, not
an end-of-session edit. At least 6 of 547 segments sit in the danger band, so this is not rare.

## Defect 2 (measured, not fixed) â€” the fingerprint invalidates itself

`package_fingerprint` hashes **every `*.py` in the package**, so any edit â€” including this change's
own lint fix â€” invalidates the provisioned runtime, and the pipeline says "not provisioned" again.
Seven fingerprint directories had already accumulated here, four with `.ready`. The venv is shared so
re-provisioning is cheap (`Checked 3 packages in 1.80s`), but the message cannot distinguish *never
provisioned* from *provisioned, then the source changed* â€” the conflation D-131 fixed for
downloaded-versus-runnable.

Gate: `VERIFY OK â€” 1190 passed, 0 skipped`.
