# Linux ffmpeg source identity — 2026-08-09

`scripts/fetch-ffmpeg.sh` previously downloaded this mutable path and unpacked it without a
digest:

`https://media.githubusercontent.com/media/zackees/ffmpeg_bins/main/v8.0/linux.zip`

The upstream repository and Git-LFS pointer were inspected directly:

| Field | Recorded value |
|---|---|
| Repository | `zackees/ffmpeg_bins` |
| Commit | `df95abcb0ce6efff710dda5ef28a2f6f1dc21493` |
| Path | `v8.0/linux.zip` |
| Git-LFS object SHA-256 | `ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad` |
| Git-LFS object size | `142008975` bytes |

The immutable media URL was then downloaded on hawapc01: the response was exactly 142,008,975
bytes and independently hashed to the same `ca75b05e…c14ad` value.

The fetcher now addresses that exact commit, requires HTTPS, retries transport failures, and
checks the LFS SHA-256 before `unzip` runs. A mismatch deletes the downloaded archive and exits;
no executable bytes are extracted or installed.

This pins the project-fetched Linux build. A system ffmpeg supplied by the Windows/macOS package
manager remains an external deployment dependency and is capability-checked for libass,
HarfBuzz and FriBidi at runtime.
