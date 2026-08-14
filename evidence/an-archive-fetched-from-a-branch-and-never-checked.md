# An archive fetched from a branch, and never checked

> Measured 2026-08-09 on hawapc01 against `90fb8ba`.

`fetch-ffmpeg.sh` downloads a 142 MB archive, unzips it, marks it executable and runs it. That is
the most privileged thing this repository does with bytes from the internet, and it was the least
verified.

```
url=…/zackees/ffmpeg_bins/main/v8.0/linux.zip      a branch path
curl -sSL -o linux.zip "$url"                       no --fail
unzip -oq … ; chmod +x … ; "${dest}/ffmpeg" -version
```

No digest anywhere. And the repository disagreed with itself about it:

```
README.md:255                 "fetches the pinned ffmpeg"           false
.github/workflows/gate.yml    "fetch the pinned ffmpeg"             false
        (same file)           "fetch-ffmpeg.sh pins the URL."       false
AUDIT_REPORT.md               "fetch-ffmpeg.sh is still unpinned"   true
```

## What the endpoint actually allows

The obstacle was never the host. Checked before writing anything:

```
GET api.github.com/repos/zackees/ffmpeg_bins/commits/main
  df95abcb0ce6efff710dda5ef28a2f6f1dc21493   2026-01-16T20:09:43Z
  "Add FFmpeg v8.0 binaries for all platforms including ARM64 (with LFS)"

HEAD …/media/zackees/ffmpeg_bins/main/v8.0/linux.zip        200  142,008,975
HEAD …/media/zackees/ffmpeg_bins/df95abcb…/v8.0/linux.zip   200  142,008,975
```

The Git-LFS media endpoint serves a commit ref. Both were then downloaded in full:

```
linux-pinned.zip  142,008,975  ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad
linux-main.zip    142,008,975  ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad
identical: True
```

So pinning changes nothing about today's bytes and everything about tomorrow's.

## What changed

```
ffmpeg_bins_commit="df95abcb0ce6efff710dda5ef28a2f6f1dc21493"
linux_zip_sha256="ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad"
url=…/${ffmpeg_bins_commit}/v8.0/linux.zip
curl --fail --location --proto '=https' --tlsv1.2 -o "$private_stage/linux.zip" "$url"
bash verify-sha256.sh "$private_stage/linux.zip" "$linux_zip_sha256"
                                                   <- before unzip or executable publication
```

The digest is **ours**, and the record says so: the project publishes none, which is why the audit
said there was nothing to compare against. This one attests *"these are the bytes hawapc01 and CI
have been running"* — weaker than a publisher's signature, immeasurably stronger than nothing.

The integrated installer is stricter than the first patch measured above: a kernel lock protects
one owner-controlled install root; download, digest verification, unzip and RTL capability probes
all happen in a private attempt directory; and only an immutable generation with a SHA-256 receipt
is published. Interrupted or corrupt attempts cannot become the `ffmpeg` launcher.

## Proof

Against the real archives, through the real script and the digest recorded in it:

```
$ bash scripts/verify-sha256.sh linux-pinned.zip ca75b05e…   sha256 OK  exit 0
$ bash scripts/verify-sha256.sh linux-main.zip   ca75b05e…   sha256 OK  exit 0
$ bash scripts/verify-sha256.sh probe.bin        0000…       ✗ does not match  exit 1
      expected  0000000000000000000000000000000000000000000000000000000000000000
      actual    ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
$ bash scripts/verify-sha256.sh probe.bin        CA75B05E…   ✗ not a lowercase hex SHA-256  exit 2
$ bash scripts/verify-sha256.sh absent.bin       0000…       ✗ does not exist  exit 2
```

**The download itself cannot run here.** The archive is Linux-only and this machine has a conforming
ffmpeg on `PATH`, so the script short-circuits — measured, it prints the Gyan 8.1.1 build and exits
before any download. CI exercises the pinned URL and the digest on every push; that is the gate of
record earning its name, not a gap in this evidence.

## The audit caught the test being prose-shaped, twice

```
first run

RED   the URL points at a branch again (the defect)
RED   the digest is never compared
RED   the digest is compared after the archive is unpacked
GREEN — SURVIVED  curl no longer fails on an HTTP error
RED   a mismatching digest is accepted
RED   an upper-case or truncated digest is compared instead of refused
RED   a file that does not exist reads as verified

6/7
```

The survivor: the test asserted `"--fail" in fetch-ffmpeg.sh`, and the script *explains* `--fail` in
a comment directly above the call. The ordering test one function up had failed the same way minutes
earlier — it matched *"Before unzip, before chmod +x"* in prose and reported the order backwards.
Both read code lines now, and the audit is **7/7**.

The executable tests use three-byte probes for both digest outcomes; the hosted Linux gate performs
the full pinned archive download and then requires the real Kurdish golden render to run.
