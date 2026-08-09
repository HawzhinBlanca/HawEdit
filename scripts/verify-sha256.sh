#!/usr/bin/env bash
# Refuse a downloaded file whose SHA-256 is not the one recorded for it.
#
#   bash scripts/verify-sha256.sh FILE EXPECTED_SHA256
#
# Its own script rather than four lines inside `fetch-ffmpeg.sh`, for one reason: the branch it
# exists for is the one that must never be reached, so it has to be reachable from a test. The
# ffmpeg archive is 142 MB and no test is going to download it to prove a mismatch is refused;
# this takes three bytes and both answers. D-121.
#
# `sha256sum` is coreutils and ships with Git for Windows; `shasum -a 256` is the macOS spelling.
# Refusing when neither exists is deliberate — computing no digest and continuing is the state
# this replaces.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "✗ usage: bash scripts/verify-sha256.sh FILE EXPECTED_SHA256" >&2
  exit 2
fi

file="$1"
expected="$2"

if [[ ! -f "$file" ]]; then
  echo "✗ $file does not exist, so there is nothing to verify" >&2
  exit 2
fi

if [[ ! "$expected" =~ ^[0-9a-f]{64}$ ]]; then
  echo "✗ '$expected' is not a lowercase hex SHA-256. A truncated or upper-case digest would" >&2
  echo "  compare unequal against every real file and read as tampering." >&2
  exit 2
fi

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$file" | cut -d' ' -f1)"
else
  echo "✗ no sha256sum or shasum on this machine, so the download cannot be verified." >&2
  echo "  Refusing rather than executing 142 MB of unchecked bytes." >&2
  exit 2
fi

if [[ "$actual" != "$expected" ]]; then
  echo "✗ $file does not match the recorded digest." >&2
  echo "    expected  $expected" >&2
  echo "    actual    $actual" >&2
  echo "  The bytes behind the pinned URL changed, the download was corrupted, or something in" >&2
  echo "  between substituted them. This archive is unzipped and executed, so it stops here." >&2
  exit 1
fi

echo "sha256 OK  $(basename "$file")"
