# Atomic delivery bundle evidence · 2026-08-09

## Claim under test

A HawEdit delivery is public only as one complete, write-once directory containing exactly:

```text
<clip-id>.ass
<clip-id>.mp4
<clip-id>.srt
<clip-id>.edl
<clip-id>.json
```

The public commit point is a same-filesystem directory rename after every member is regular,
non-empty and flushed. A failed worker must not expose its rendered MP4 or any sidecar.

## Focused measurement

Environment: Windows, Python from the project development environment, current worktree source
forced first on `PYTHONPATH` so the parallel checkout's editable install cannot mask changes.

```text
pytest -q tests/test_artifact_bundle.py tests/test_transcripts.py tests/test_pipeline.py
124 passed
ruff check: passed
mypy (artifact_bundle.py, pipeline.py, transcripts.py): passed
```

The complete project gate then reported `1,140 collected, 1,140 passed, 0 skipped` with Ruff,
format checking and mypy clean. `scripts/test-count.floor` ratcheted to 1,140.

The real 4.162 s media fixture completes one exact five-file directory. Injecting failure at
the first ASS write and after JSON but before SRT produces `StageSkipped` and leaves no final
directory or hidden staging directory. Unsupported 24000/1001 EDL construction likewise
publishes nothing. The existing NTSC test still publishes a complete 30000/1001 drop-frame set.

## Race and recovery measurement

Two workers stage distinct marker payloads behind a barrier and publish the same clip id. The
observed result is one `published`, one `refused`; all five public payloads carry one worker's
marker. Missing members, an empty member, an extra member and a pre-existing final directory are
all refused. A deliberately abandoned hidden staging directory does not block a second worker's
clean publication; explicit cleanup removes only the known direct files and refuses unexpected
directories.

## Boundary of the claim

This proves atomic visibility and write-once ownership in the filesystem namespace. File bytes
are flushed before rename. It does not simulate controller-level power loss or claim stronger
directory-metadata durability than the host filesystem provides. A killed process may leave a
hidden staging directory; it never makes that directory a public delivery and does not block a
retry.
