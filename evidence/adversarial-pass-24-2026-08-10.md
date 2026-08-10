# Adversarial pass 24 - release publication cannot replace an empty winner

Date: 2026-08-10
Baseline: `5b3442f491ac79868f6a2281c6cfb85ffbd59041`

## Finding

The release builder checked that its final directory did not exist and then called `os.rename`.
The test covered a populated winner, which POSIX already refuses to replace. It did not cover an
empty directory created by another process after the check. POSIX `rename` may replace that empty
directory atomically, so the operation was atomic but not write-once.

That distinction is load-bearing for release output: an external process can reserve the final
name between a successful preflight and publication, and the release process must preserve that
winner regardless of whether it has written its first file yet.

## Fix and proof

Release publication now delegates to the shared native no-replace primitive introduced by
adversarial pass 23. A kernel `EEXIST`/`ENOTEMPTY` becomes the same bounded `ReleaseError`; other
filesystem failures keep their existing domain error. There is no check-then-rename fallback.

The discriminating regression creates an empty final directory, records its inode, and invokes the
real release publication function. The call refuses, the inode and empty contents remain unchanged,
and the private staged wheel remains intact. The older populated-winner control still passes.
