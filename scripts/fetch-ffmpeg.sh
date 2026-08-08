#!/usr/bin/env bash
# Fetch an ffmpeg build that can actually render Kurdish captions (§4.3).
#
# §4.3.2 is emphatic that a build accepting `shaping=complex` may still lack the backing
# library, so this script verifies libass + HarfBuzz + FriBidi after downloading and refuses
# a build that cannot shape Arabic script.
#
# The binary is ~200 MB and is NOT committed. It lands in .ffmpeg/ (git-ignored).
#
# Usage:  bash scripts/fetch-ffmpeg.sh
# Then:   export HAWEDIT_FFMPEG="$PWD/.ffmpeg/ffmpeg"
#
# LICENCE NOTE: this build is --enable-gpl --enable-version3. See DECISIONS.md D-021 —
# ffmpeg is invoked as a separate executable, which is the standard arrangement and does not
# place this project's own source under the GPL. Confirm before shipping a bundled binary.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
dest="${here}/.ffmpeg"
mkdir -p "$dest"

# Immutable source and content identity. The second value is the Git-LFS object's own SHA-256,
# read from v8.0/linux.zip's pointer at this exact commit. A commit-pinned URL prevents a branch
# move; the digest independently prevents a compromised/misrouted response from being unpacked.
ffmpeg_bins_commit="df95abcb0ce6efff710dda5ef28a2f6f1dc21493"
linux_zip_sha256="ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad"

# §4.3.2's requirement is a *verified* build, not a downloaded one. Check what is already
# reachable before spending 200 MB — and check it the same way, so an ffmpeg accepted from
# PATH has cleared exactly the bar a fetched one clears. `captions.find_ffmpeg` resolves
# HAWEDIT_FFMPEG, then .ffmpeg/, then PATH, and this looks in the same order for the same
# reason: the script and the library must not disagree about which binary is in play.
verify_rtl() {
  local binary="$1" buildconf missing=()
  buildconf="$("$binary" -hide_banner -buildconf 2>&1)" || return 1
  for lib in libass libharfbuzz libfribidi; do
    grep -q -- "--enable-${lib}" <<<"$buildconf" || missing+=("$lib")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "   ${binary}: lacks ${missing[*]}" >&2
    return 1
  fi
}

for existing in "${HAWEDIT_FFMPEG:-}" "${dest}/ffmpeg" "${dest}/ffmpeg.exe" "$(command -v ffmpeg || true)"; do
  [[ -n "$existing" && -x "$existing" ]] || continue
  if verify_rtl "$existing"; then
    "$existing" -version | head -1
    echo "libass + HarfBuzz + FriBidi: present — nothing to fetch"
    echo "using: ${existing}"
    exit 0
  fi
done

if [[ "$(uname -s)" != Linux* ]]; then
  # The archive below is a Linux build. Downloading it here would produce a file that cannot
  # execute, and the verification step would then report a missing RTL stack — a true-sounding
  # error about the wrong thing. Say what is actually needed instead.
  echo "REFUSED: no ffmpeg with libass + HarfBuzz + FriBidi is reachable, and the build this" >&2
  echo "script fetches is Linux-only. Install one for this platform and re-run, e.g.:" >&2
  echo "  Windows:  winget install Gyan.FFmpeg     (the 'full' build carries the RTL stack)" >&2
  echo "  macOS:    brew install ffmpeg" >&2
  echo "Then point HAWEDIT_FFMPEG at it, or leave it on PATH — both are discovered." >&2
  exit 1
fi

if [[ -x "${dest}/ffmpeg" ]]; then
  echo "ffmpeg already present at ${dest}/ffmpeg"
else
  # Served through the Git-LFS media endpoint: the plain raw.githubusercontent URL returns a
  # 134-byte LFS pointer, not the archive.
  url="https://media.githubusercontent.com/media/zackees/ffmpeg_bins/${ffmpeg_bins_commit}/v8.0/linux.zip"
  echo "==> downloading ffmpeg (~140 MB) from ${url}"
  curl --fail --silent --show-error --location --retry 3 \
    --proto '=https' --tlsv1.2 -o "${dest}/linux.zip" "$url"
  echo "${linux_zip_sha256}  ${dest}/linux.zip" | sha256sum --check --status || {
    actual="$(sha256sum "${dest}/linux.zip" | cut -d' ' -f1)"
    rm -f "${dest}/linux.zip"
    echo "REFUSED: ffmpeg archive SHA-256 ${actual} did not match ${linux_zip_sha256}." >&2
    echo "Nothing was extracted or installed." >&2
    exit 1
  }
  unzip -oq "${dest}/linux.zip" -d "${dest}/extract"
  find "${dest}/extract" -name ffmpeg -type f -exec cp {} "${dest}/ffmpeg" \;
  find "${dest}/extract" -name ffprobe -type f -exec cp {} "${dest}/ffprobe" \;
  chmod +x "${dest}/ffmpeg" "${dest}/ffprobe"
  rm -rf "${dest}/linux.zip" "${dest}/extract"
fi

echo "==> verifying the RTL stack (§4.3.2)"
if ! verify_rtl "${dest}/ffmpeg"; then
  echo "REFUSED: this ffmpeg cannot shape Arabic script correctly." >&2
  echo "§4.3: the failure is invisible until a client sees the burned-in captions." >&2
  exit 1
fi

"${dest}/ffmpeg" -version | head -1
echo "libass + HarfBuzz + FriBidi: present"
echo
echo "export HAWEDIT_FFMPEG=\"${dest}/ffmpeg\""
