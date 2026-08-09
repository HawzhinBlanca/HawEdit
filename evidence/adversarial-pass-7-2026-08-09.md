# Adversarial pass #7 â€” invariants #1 and #3, against the real run's artifacts

> Run 2026-08-09 on hawapc01 against `771ca17`.
> Target: **M0.4**, DONE â€” "#1 enforced three ways (refuse-rewrite, frozen types, SHA-256 tamper
> evidence); #3 enforced by distinct types (mypy) + `assert_model_input` (runtime) + stale-norm
> detection. ASR provenance is validated against Â§7 at construction."

Every previous pass used fixtures. This one used the artifacts 38 minutes of Kurdish actually produced,
on a copy, so the originals were never modified â€” verified afterwards: the real file still matches its
sidecar.

## Part 1 â€” the invariants, on the real 820,835-byte transcript

```
real artifact under test: zar38final.transcript.raw.json, 820,835 bytes
  words 6,104   text 35,166 chars   unaligned 2

attack                                       verdict
sidecar matches the 820 KB artifact          HELD
a second write of identical content          REFUSED
one tampered byte                            DETECTED
a norm from a different raw                  REFUSED

invariants broken: 0
```

**A measurement I nearly got wrong.** The first reading of the file mode said `-rw-rw-rw-`, which would
have contradicted the docstring's `chmod 0o444`. It was my own tamper step's `chmod(S_IWRITE)`, three
lines earlier. Re-measured on the untouched artifact and on a fresh write: both `-r--r--r--` `0o444`.
The claim holds; the harness was lying.

## Part 2 â€” revert each mechanism, check the test goes red

```
baseline FAILED=0
RED    #1 way 1a: the sidecar's write-once link no longer refuses     (8 tests)
GREEN  #1 way 1b: the raw file's write-once link no longer refuses    <- UNPROTECTED
RED    #1 way 3:  SHA-256 tamper evidence never fires                 (2 tests)
RED    #3:        stale-norm detection never fires                    (1 test)
RED    #3:        assert_model_input stops refusing a raw transcript  (2 tests)
RED    provenance: Â§7 role validation at construction                 (2 tests)
RED    #1 way 2:  the frozen type becomes mutable                     (1 test)
RED    #1 way 3a: the advisory read-only mode is dropped              (1 test)
control: a no-op edit                                                 GREEN, as it must be
```

`write_raw` refuses twice over and only the first refusal was tested. The sidecar's link is published
first, so it refuses first in every path a test exercised, and the raw file's own link was never
reached.

**It is not dead code.** It is the layer that matters when the sidecar is *gone* â€” the state someone
hiding a modification would create, because `verify_raw_integrity` needs that digest to detect
anything. Measured in that state:

```
state: raw exists = True | sidecar exists = False
second write REFUSED by the raw-file layer
raw content unchanged      : True
a sidecar was left behind  : False
staging files left in dir  : ['m.transcript.raw.json']
```

## The fix, and a correction to my own method

Two tests: one deletes the sidecar and asserts the refusal, the unchanged bytes, the absent sidecar and
the clean directory; a control asserts that with both artifacts present the refusal still comes from the
first layer. The messages differ â€” "already exists or is being written" versus "already exists." â€” so
the control cannot be satisfied by breaking the layer the other test covers.

**Five of my first results were false.** The initial harness replaced each `raise X(` line with `pass`,
orphaning the multi-line message and making the module unparseable, so five mechanisms reported RED on a
`SyntaxError` rather than on a caught regression â€” D-082's wrong-reason catch, produced by the audit
itself. The rewritten harness neutralises the *condition* and asserts `import hawedit.transcripts`
succeeds before trusting any verdict. Recorded because an audit that can fabricate protection is worse
than no audit, and this is the second harness defect this week (D-136's Windows file lock was the first).

Re-run after the fix: **5/5**, with the raw-file link caught by exactly the new test.

Gate: `VERIFY OK â€” 1209 passed, 0 skipped`.
