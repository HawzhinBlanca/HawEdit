# M3.3 — NVENC on hawapc01, and the probe that said it was not there

`BLOCKED.md` #2 recorded NVENC as needing hawapc01. This checkout is on hawapc01 and the
ffmpeg on `PATH` is built `--enable-nvenc`. Both true, and `encoder_available` still said no.

## The defect

`render.encoder_available` exists because a capability listing cannot be trusted — its
docstring says so, quoting §4.3.2: "a build accepting the option may still lack the backing
library". It answered by encoding one real frame and checking bytes came out.

**It encoded that frame at 64x64, and NVENC will not encode a frame that small.**

```
[h264_nvenc] InitializeEncoder failed: invalid param (8):
             Frame Dimension less than the minimum supported value.
[out#0/mp4]  Nothing was written into output file, because at least one of its
             streams received no packets.
```

Note the exit status: ffmpeg returned **0**. The probe's own comment anticipated that —
"ffmpeg can exit 0 having written nothing" — and the byte check caught it correctly. The
probe was not lying about what it saw. It was asking the wrong question.

Measured on this box, same binary, same encoder, one frame each:

| Frame size | Bytes written |
|---|---|
| 64x64 | **0** |
| 128x128 | **0** |
| 145x49 | 1032 |
| 1080x1920 | 1300 |

So the function written *because* a listing cannot be trusted was itself returning a confident
wrong answer — and `render_clip` refuses an unavailable encoder rather than substituting
(deliberately, §6), which means **asking for NVENC on hawapc01 would have raised.** The one
machine the blueprint puts NVENC on is the one machine where this said NVENC was absent.

## The fix

The probe encodes at `ENCODER_PROBE_SIZE`, which is Stage 6's own output geometry
(`VERTICAL_WIDTH × VERTICAL_HEIGHT` = 1080×1920). The question `render_clip` needs answered is
"can this encoder encode what Stage 6 will hand it", so that is the frame the probe hands it.
`NVENC_MIN_FRAME = (145, 49)` records the measurement above, and a test asserts the probe is
not smaller than it — that test needs no ffmpeg and no GPU, so it holds on a CI runner too.

The two tests that had hardcoded "this machine has no GPU" were rewritten. One asserted NVENC
was *unavailable*, so it was built to go red the moment the project reached its own hardware;
it now asserts the property in both directions — what `encoder_available` reports equals
whether an independently-spelled real encode writes bytes. The other skipped itself when NVENC
worked, which is a skip on precisely the box the rule is about; it now answers availability
directly and exercises the refusal everywhere.

## The result — a real clip, encoded on the GPU

`render_clip` over `tests/fixtures/kurdish-speech-3cuts.mp4`, same clip, both encoders:

| Encoder | Output | Requested | Measured | Captions | Reframe | Bytes | Wall |
|---|---|---|---|---|---|---|---|
| `libx264` | 1080×1920 | 2200 ms | 2240 ms | yes | `static_centre` | 49 921 | 0.90 s |
| `h264_nvenc` | 1080×1920 | 2200 ms | 2240 ms | yes | `static_centre` | 55 320 | 1.35 s |

`evidence/m3-3-nvenc-clip.mp4` is the NVENC render. Both clear `assert_encoded_span` — the
measured span comes from probing the written file (M3.4), not from echoing the request.

Captions verified on decoded pixels rather than on the flag, NVENC against NVENC:

```
NVENC captioned vs uncaptioned: 12049 of 6220800 bytes differ (0.2%)
```

A captioned render must differ from an uncaptioned one; if libass had drawn nothing the frames
would be identical, which is exactly the failure M3.5 found on the x264 path.

**Wall-clock is not a throughput claim.** 1.35 s against 0.90 s on a 2.2-second clip is
dominated by encoder session setup, and §3 Stage 1's warning about turning published figures
into wall-clock promises applies to encoders too. NVENC's case here is that it works and that
Stage 6 can now use it, not that it is faster on a 2-second fixture.

## What is still open on M3.3

The row stays **PARTIAL**, and the reason is unchanged: §3 Stage 6 reframes by tracking the
active speaker from diarization plus face detection. Diarization needs the gated Community-1
repo, measured **401** from here (`evidence/hawapc01-environment.md`), so the crop is still
static and still says so by name — `Reframe.STATIC_CENTRE`, never `SPEAKER_TRACKED`.
NVENC was one of that row's two shortfalls. It is now the one.
