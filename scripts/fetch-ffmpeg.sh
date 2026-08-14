#!/usr/bin/env bash
# Fetch an ffmpeg build that can actually render Kurdish captions (section 4.3).
#
# The fetched Linux build is content-addressed, verified in a private generation, and exposed
# through two tiny launchers only after both ffmpeg and ffprobe pass.  A failed or interrupted
# attempt therefore cannot make a partial download look installed, and the next run can repair a
# corrupt previous installation.
#
# Usage:  bash scripts/fetch-ffmpeg.sh
# Then:   export HAWEDIT_FFMPEG="$PWD/.ffmpeg/ffmpeg"
#
# LICENCE NOTE: this build is --enable-gpl --enable-version3. See DECISIONS.md D-021. ffmpeg is
# invoked as a separate executable; confirm the redistribution obligations before bundling it.
set -euo pipefail
umask 077

here="$(cd "$(dirname "$0")/.." && pwd -P)"
dest="${HAWEDIT_FFMPEG_DIR:-${here}/.ffmpeg}"

# Immutable source and content identity. The digest is the Git-LFS object's SHA-256 at the exact
# commit. The commit prevents branch movement; the digest independently authenticates the bytes.
ffmpeg_bins_commit="df95abcb0ce6efff710dda5ef28a2f6f1dc21493"
linux_zip_sha256="ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad"

refuse() {
  echo "REFUSED: $*" >&2
  exit 1
}

case "$dest" in
  /* | [A-Za-z]:/*) ;;
  *) refuse "HAWEDIT_FFMPEG_DIR must be an absolute path when it is set." ;;
esac

prepare_install_root() {
  if [[ -L "$dest" ]]; then
    refuse "${dest} is a symbolic link; ffmpeg installation requires an owned directory."
  fi
  if [[ -e "$dest" && ! -d "$dest" ]]; then
    refuse "${dest} exists and is not a directory."
  fi
  if [[ ! -e "$dest" ]]; then
    mkdir -p -- "$dest"
    chmod 700 -- "$dest"
  fi
  if [[ -L "$dest" || ! -d "$dest" ]]; then
    refuse "${dest} changed while the install root was being prepared."
  fi

  # Resolve after creation. This catches a linked final component even on systems whose `test -L`
  # does not expose directory reparse points.
  local resolved expected owner mode
  resolved="$(cd -P "$dest" && pwd -P)"
  expected="${here}/.ffmpeg"
  if [[ "$resolved" != "$expected" ]]; then
    refuse "${dest} resolves outside its checkout (${resolved})."
  fi

  # Downloads occur only on Linux. Refuse a root another account can replace or mutate while curl,
  # unzip, and verification are running. Read/execute permissions for other users are harmless.
  if [[ "$(uname -s)" == Linux* ]]; then
    owner="$(stat -c '%u' -- "$dest")"
    mode="$(stat -c '%a' -- "$dest")"
    if [[ "$owner" != "$(id -u)" ]]; then
      refuse "${dest} is owned by uid ${owner}, not the current uid $(id -u)."
    fi
    if (( (8#$mode & 0022) != 0 )); then
      refuse "${dest} mode ${mode} permits another account to mutate the install root."
    fi
  fi
}

# Section 4.3.2 requires a verified build, not merely a process named ffmpeg.
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

verify_pair() {
  local ffmpeg="$1" ffprobe="$2"
  [[ -x "$ffmpeg" && -x "$ffprobe" ]] || return 1
  verify_rtl "$ffmpeg" || return 1
  "$ffprobe" -hide_banner -version >/dev/null 2>&1 || return 1
}

launcher_matches() {
  local launcher="$1" generation_name="$2" program="$3" expected actual
  [[ -f "$launcher" && ! -L "$launcher" ]] || return 1
  # The launcher evaluates these variables when it runs, not while this template is built.
  # shellcheck disable=SC2016
  expected="$(printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'self_dir="$(cd "$(dirname "$0")" && pwd -P)"' \
    "exec \"\${self_dir}/generations/${generation_name}/${program}\" \"\$@\"")"
  actual="$(cat -- "$launcher")" || return 1
  [[ "$actual" == "$expected" ]]
}

verify_fetched_install() {
  local marker="${dest}/current-generation" generation_name extra generation
  [[ -f "$marker" && ! -L "$marker" ]] || return 1
  IFS= read -r generation_name <"$marker" || return 1
  IFS= read -r extra < <(sed -n '2p' -- "$marker") || true
  [[ -z "$extra" && "$generation_name" =~ ^[0-9a-f]{16}-[A-Za-z0-9]+$ ]] || return 1
  generation="${dest}/generations/${generation_name}"
  [[ -d "$generation" && ! -L "$generation" ]] || return 1
  launcher_matches "${dest}/ffmpeg" "$generation_name" ffmpeg || return 1
  launcher_matches "${dest}/ffprobe" "$generation_name" ffprobe || return 1
  (
    cd "$generation"
    sha256sum --check --status SHA256SUMS
  ) || return 1
  verify_pair "${dest}/ffmpeg" "${dest}/ffprobe"
}

prepare_install_root

# A fetched local installation is accepted only when its exact launchers and the bytes of both
# generation members still match the receipt written after the authenticated archive was unpacked.
if [[ -x "${dest}/ffmpeg" ]]; then
  if verify_fetched_install; then
    "${dest}/ffmpeg" -version 2>&1 | sed -n '1p'
    echo "libass + HarfBuzz + FriBidi: present - fetched generation and hashes verified"
    echo "using: ${dest}/ffmpeg"
    exit 0
  fi
  echo "   ${dest}/ffmpeg: fetched receipt or bytes are invalid; repairing" >&2
fi

# Explicit operator-supplied, Windows-local, and PATH builds are capability-verified. They are not
# represented as HawEdit-fetched bytes, so the script makes no false content-identity claim for them.
for existing in "${HAWEDIT_FFMPEG:-}" "${dest}/ffmpeg.exe" "$(command -v ffmpeg || true)"; do
  [[ -n "$existing" && -x "$existing" ]] || continue
  [[ "$existing" != "${dest}/ffmpeg" ]] || continue
  if verify_rtl "$existing"; then
    "$existing" -version 2>&1 | sed -n '1p'
    echo "libass + HarfBuzz + FriBidi: present - nothing to fetch"
    echo "using: ${existing}"
    exit 0
  fi
done

if [[ "$(uname -s)" != Linux* ]]; then
  echo "REFUSED: no ffmpeg with libass + HarfBuzz + FriBidi is reachable, and the build this" >&2
  echo "script fetches is Linux-only. Install one for this platform and re-run, e.g.:" >&2
  echo "  Windows:  winget install Gyan.FFmpeg     (the 'full' build carries the RTL stack)" >&2
  echo "  macOS:    brew install ffmpeg" >&2
  echo "Then point HAWEDIT_FFMPEG at it, or leave it on PATH - both are discovered." >&2
  exit 1
fi

# A stable kernel lock releases even after SIGKILL. Opening read/write does not truncate a planted
# hardlink; single-link/type/owner/mode checks refuse one before flock. The /proc comparison binds the
# descriptor to the path on real Linux, closing replacement between the path checks and acquisition.
command -v flock >/dev/null 2>&1 || refuse "Linux ffmpeg provisioning requires util-linux flock."
lock_file="${dest}/.fetch.lock"
if [[ -L "$lock_file" || ( -e "$lock_file" && ! -f "$lock_file" ) ]]; then
  refuse "${lock_file} is not a regular lock file."
fi
if [[ ! -e "$lock_file" ]]; then
  ( set -o noclobber; : >"$lock_file" ) 2>/dev/null || true
fi
[[ -f "$lock_file" && ! -L "$lock_file" ]] || refuse "cannot create a regular ffmpeg lock."
lock_owner="$(stat -Lc '%u' -- "$lock_file")"
lock_mode="$(stat -Lc '%a' -- "$lock_file")"
lock_links="$(stat -Lc '%h' -- "$lock_file")"
if [[ "$lock_owner" != "$(id -u)" || "$lock_links" != 1 || $((8#$lock_mode & 0022)) -ne 0 ]]; then
  refuse "${lock_file} must be one owner-controlled regular file."
fi
lock_path_identity="$(stat -Lc '%d:%i:%h' -- "$lock_file")"
lock_fd=""
exec {lock_fd}<>"$lock_file" || refuse "cannot open ${lock_file} without truncating it."
if [[ -e "/proc/$$/fd/${lock_fd}" ]]; then
  lock_fd_identity="$(stat -Lc '%d:%i:%h' -- "/proc/$$/fd/${lock_fd}")"
  [[ "$lock_fd_identity" == "$lock_path_identity" ]] || \
    refuse "${lock_file} changed while its descriptor was opened."
fi
if ! flock -n "$lock_fd"; then
  refuse "another ffmpeg provisioner holds ${lock_file}."
fi
[[ ! -L "$lock_file" && "$(stat -Lc '%d:%i:%h' -- "$lock_file")" == "$lock_path_identity" ]] || \
  refuse "${lock_file} changed while its lock was acquired."

stage=""
cleanup() {
  local status=$?
  if [[ -n "$stage" && -d "$stage" && ! -L "$stage" && "$stage" == "${dest}/.fetch."* ]]; then
    rm -rf -- "$stage"
  fi
  if [[ -n "$lock_fd" ]]; then
    if ! flock -u "$lock_fd"; then
      echo "REFUSED: cannot release the ffmpeg provision lock." >&2
      [[ $status -ne 0 ]] || status=1
    fi
    exec {lock_fd}>&-
  fi
  return "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

stage="$(mktemp -d "${dest}/.fetch.XXXXXXXX")"
[[ "$stage" == "${dest}/.fetch."* && -d "$stage" && ! -L "$stage" ]] || \
  refuse "mktemp did not create a private ffmpeg stage under ${dest}."

archive="${stage}/linux.zip"
extract="${stage}/extract"
payload="${stage}/payload"
url="https://media.githubusercontent.com/media/zackees/ffmpeg_bins/${ffmpeg_bins_commit}/v8.0/linux.zip"

echo "==> downloading ffmpeg (~140 MB) from ${url}"
# `--retry-all-errors` is load-bearing: the hosted gate observed curl exit 92 (HTTP/2
# PROTOCOL_ERROR) after 100 seconds, and plain `--retry` does not cover that transport class.
# A retried partial transfer is still refused by the exact digest before unzip. D-123.
curl --fail --silent --show-error --location --retry 3 --retry-delay 2 --retry-all-errors \
  --proto '=https' --tlsv1.2 -o "$archive" "$url"
bash "$(dirname "$0")/verify-sha256.sh" "$archive" "$linux_zip_sha256" || \
  refuse "ffmpeg archive SHA-256 did not match; nothing was unpacked or published."

mkdir -m 700 -- "$extract" "$payload"
unzip -q "$archive" -d "$extract"
mapfile -d '' -t ffmpeg_hits < <(find "$extract" -type f -name ffmpeg -print0)
mapfile -d '' -t ffprobe_hits < <(find "$extract" -type f -name ffprobe -print0)
if [[ ${#ffmpeg_hits[@]} -ne 1 || ${#ffprobe_hits[@]} -ne 1 ]]; then
  refuse "the authenticated archive did not contain exactly one ffmpeg and one ffprobe."
fi
install -m 700 -- "${ffmpeg_hits[0]}" "${payload}/ffmpeg"
install -m 700 -- "${ffprobe_hits[0]}" "${payload}/ffprobe"

echo "==> verifying the staged RTL stack (section 4.3.2)"
verify_pair "${payload}/ffmpeg" "${payload}/ffprobe" || \
  refuse "the staged ffmpeg/ffprobe pair failed RTL or executable verification; nothing was published."
(cd "$payload" && sha256sum ffmpeg ffprobe >SHA256SUMS)

# One immutable generation owns the pair. The ffprobe launcher is exposed first and the ffmpeg
# launcher (the discovery/commit marker) last. Once ffmpeg is visible, both launchers address the
# already-verified generation. A crash before that point is repairable on the next invocation.
generations="${dest}/generations"
if [[ -L "$generations" || ( -e "$generations" && ! -d "$generations" ) ]]; then
  refuse "${generations} is not a safe generation directory."
fi
mkdir -p -- "$generations"
chmod 700 -- "$generations"
generation_owner="$(stat -c '%u' -- "$generations")"
generation_mode="$(stat -c '%a' -- "$generations")"
if [[ "$generation_owner" != "$(id -u)" || $((8#$generation_mode & 0022)) -ne 0 ]]; then
  refuse "${generations} is not an owner-controlled generation directory."
fi
generation_name="${linux_zip_sha256:0:16}-$(basename "$stage" | sed 's/^\.fetch\.//')"
generation="${generations}/${generation_name}"

make_launcher() {
  local output="$1" program="$2"
  # The generated launcher evaluates this line from its own installed location.
  # shellcheck disable=SC2016
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'self_dir="$(cd "$(dirname "$0")" && pwd -P)"' \
    "exec \"\${self_dir}/generations/${generation_name}/${program}\" \"\$@\"" \
    >"$output"
  chmod 700 -- "$output"
}

for target in "${dest}/ffmpeg" "${dest}/ffprobe" "${dest}/current-generation"; do
  if [[ -d "$target" && ! -L "$target" ]]; then
    refuse "${target} is a directory and will not be replaced."
  fi
done
make_launcher "${stage}/ffprobe.launcher" ffprobe
make_launcher "${stage}/ffmpeg.launcher" ffmpeg
printf '%s\n' "$generation_name" >"${stage}/current-generation"
mv -- "$payload" "$generation"
mv -fT -- "${stage}/current-generation" "${dest}/current-generation"
mv -fT -- "${stage}/ffprobe.launcher" "${dest}/ffprobe"
mv -fT -- "${stage}/ffmpeg.launcher" "${dest}/ffmpeg"

verify_fetched_install || \
  refuse "the published ffmpeg generation failed final verification; rerun to repair it."

"${dest}/ffmpeg" -version 2>&1 | sed -n '1p'
echo "libass + HarfBuzz + FriBidi: present"
echo
echo "export HAWEDIT_FFMPEG=\"${dest}/ffmpeg\""
