# Adding a field re-dated every transcript ever written

`read_norm` decided whether a normalized transcript belonged to its raw by **re-serialising the
parsed raw object** and hashing that. So it answered with today's schema rather than with the bytes
that were stored. D-181 added one optional `adapter` field to `AsrProvenance` on 2026-08-11, and
from that moment every normalized transcript on this disk was rejected as stale.

## Measured on the real artifacts

Four real runs in `work/`, including the 38-minute `ZAR38MinTest.mp4` transcript:

```
zar38-final/zar38final.transcript.raw.json
  stored .sha256 file : 7912e7bd1d357c5ca851b3266f26baf820cb64650492f30ed943f384c69706b0
  sha256 of bytes     : 7912e7bd1d357c5ca851b3266f26baf820cb64650492f30ed943f384c69706b0
  RawTranscript.sha256: 4748ac2a3e02a8f78fb99fadf9b5b810c4e9f77ac9e9e77e7ee5cad152b4b8c2
  adapter field       : None
  bytes match stored  : True      <- invariant #1 holds
  object match stored : False     <- what read_norm compared
```

Identical for `zar38-vis8`, `zar38-visual` and `pass8-render`. The two checks disagreed about the
same untouched file:

```
verify_raw_integrity (invariant #1, bytes vs recorded):
  PASSES — the raw file is untouched

read_norm (the derived artifact the pipeline consumes):
  StaleNormalizedTranscript: work\zar38-final\transcripts\zar38final.transcript.norm.json was
  derived from raw 7912e7bd1d35… but the stored raw is 4748ac2a3e02…. Re-run normalization: a
  stale norm looks valid on inspection, which is exactly what makes it dangerous.
```

The message is wrong in every particular. The norm *was* derived from that raw. The stored raw is
`7912e7…`, not `4748ac…` — `4748ac…` is a hash of a file that has never existed on disk, only of
what this release would write if it wrote one. And the remedy it prescribes did not work either:
re-running normalization stamped the same unstable value again, so the next added field would
break it identically.

**Nothing shipped wrong to a client**, because the pipeline writes the norm and reads it back
inside one run, where the schema cannot change underneath it. What was lost is every stored
artifact: 35,185 characters of Kurdish and 6,104 word timings from the 38-minute run were
unreadable through the API that exists to read them.

## The fix: bytes are the identity, a schema is not

`write_raw` already computes `sha256(raw.to_json().encode())` — the digest of exactly the bytes it
publishes — and stores it beside the file. `verify_raw_integrity` uses it. `read_norm` was the one
place that re-derived the answer instead of reading it.

* `read_norm` compares against `self.raw_digest(media_id)`, the file on disk.
* `normalize_transcript(raw, source_sha256=…)` takes the digest. The default stays `raw.sha256()`
  because an in-memory transcript has no file, and there the object hash is the only identity there
  is.
* the pipeline passes `store.raw_digest(identifier)` — the same value `verify_raw_integrity`
  checked one line above it.
* `write_norm` **refuses** a norm whose `source_sha256` is not the stored raw's digest.

After the fix, on the same four real artifacts:

```
zar38-final    read_norm OK —  35,185 chars of Kurdish,  6,104 word timings
zar38-vis8     read_norm OK —  35,185 chars of Kurdish,  6,104 word timings
zar38-visual   read_norm OK —  35,185 chars of Kurdish,  6,104 word timings
pass8-render   read_norm OK —      29 chars of Kurdish,      4 word timings
```

## Why the guard is in `write_norm` and not at the call site

The call site is one line in `src/`, and every future producer can forget it the same way this one
did. The check belongs where they all pass through. It is deliberately invisible while a release is
young — a raw written by today's schema hashes the same either way — and fires precisely in the
case that broke: a second run over a work directory holding a raw from an earlier release.
Refusing at write time beats storing a norm that reads back as stale forever.

## Mutation audit — 3/4, and the fourth is honest

```
baseline: GREEN (1628 passed, 86 warnings in 151.58s)

CAUGHT   read_norm goes back to re-hashing the parsed object
         by 2: test_a_transcript_written_before_a_field_existed_is_not_called_stale,
               test_storing_a_norm_stamped_from_the_parsed_object_is_refused
CAUGHT   normalize_transcript ignores the digest it was handed
         by 2: (same two)
CAUGHT   write_norm stops refusing a norm stamped from the parsed object
         by 2: test_a_stale_normalized_transcript_is_detected,
               test_storing_a_norm_stamped_from_the_parsed_object_is_refused
SURVIVED the pipeline stops stamping the file digest — 1628 passed

files restored byte-identical: True
3/4 caught
suite after restore: GREEN
```

**The survivor is not a hole that a test would close.** For an artifact written by the running
release, `raw.sha256()` and `raw_digest()` are the same number — that is why the defect stayed
invisible for a day. The mutation is only observable against a raw file written by an *earlier*
schema, which inside the pipeline means a second run over a work directory carrying one, and no
unit test can stage that without staging a release boundary. What the `write_norm` guard changes is
the failure mode: with the stamp forgotten, the pipeline now **stops loudly at the write** instead
of storing a norm that every later read rejects. Recorded rather than papered over with an
`inspect.getsource` assertion that would check the spelling of a line rather than its effect.

Both new tests build the pre-`adapter` artifact by hand — `write_raw` necessarily writes today's
schema — and each carries the control that matters. The first asserts
`stored.sha256() != store.raw_digest(...)` before anything else, because if those agreed the file
would not exhibit the drift and the test would pass against the broken code too. The second stores
the same derivation with the correct digest and reads it back, so it measures where the value came
from rather than that `write_norm` refuses everything.
