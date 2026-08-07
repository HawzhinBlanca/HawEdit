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
# Then:   export HAWEDIT2_FFMPEG="$PWD/.ffmpeg/ffmpeg"
#
# LICENCE NOTE: this build is --enable-gpl --enable-version3. See DECISIONS.md D-021 —
# ffmpeg is invoked as a separate executable, which is the standard arrangement and does not
# place this project's own source under the GPL. Confirm before shipping a bundled binary.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
dest="${here}/.ffmpeg"
mkdir -p "$dest"

if [[ -x "${dest}/ffmpeg" ]]; then
  echo "ffmpeg already present at ${dest}/ffmpeg"
else
  # Served through the Git-LFS media endpoint: the plain raw.githubusercontent URL returns a
  # 134-byte LFS pointer, not the archive.
  url="https://media.githubusercontent.com/media/zackees/ffmpeg_bins/main/v8.0/linux.zip"
  echo "==> downloading ffmpeg (~140 MB) from ${url}"
  curl -sSL -o "${dest}/linux.zip" "$url"
  unzip -oq "${dest}/linux.zip" -d "${dest}/extract"
  find "${dest}/extract" -name ffmpeg -type f -exec cp {} "${dest}/ffmpeg" \;
  find "${dest}/extract" -name ffprobe -type f -exec cp {} "${dest}/ffprobe" \;
  chmod +x "${dest}/ffmpeg" "${dest}/ffprobe"
  rm -rf "${dest}/linux.zip" "${dest}/extract"
fi

echo "==> verifying the RTL stack (§4.3.2)"
buildconf="$("${dest}/ffmpeg" -hide_banner -buildconf 2>&1)"
missing=()
for lib in libass libharfbuzz libfribidi; do
  grep -q -- "--enable-${lib}" <<<"$buildconf" || missing+=("$lib")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "REFUSED: this ffmpeg lacks ${missing[*]} — it cannot shape Arabic script correctly." >&2
  echo "§4.3: the failure is invisible until a client sees the burned-in captions." >&2
  exit 1
fi

"${dest}/ffmpeg" -version | head -1
echo "libass + HarfBuzz + FriBidi: present"
echo
echo "export HAWEDIT2_FFMPEG=\"${dest}/ffmpeg\""
