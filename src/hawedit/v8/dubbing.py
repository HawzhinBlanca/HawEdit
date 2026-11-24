"""Create a local alternate-language audio track using the translated subtitle timeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import wave
from argparse import ArgumentParser
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from hawedit.captions import find_ffmpeg
from hawedit.delivery import parse_srt_times
from hawedit.ingest import probe_duration_ms


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_voice_consent(receipt: Path, reference: Path, movie: Path, language: str) -> None:
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("scope") != "podcast-dub":
        raise ValueError("Missing podcast dubbing consent")
    if not all(
        isinstance(data.get(k), str) and data[k].strip()
        for k in ("speaker", "confirmed_by", "expires_at", "evidence_file", "evidence_sha256")
    ):
        raise ValueError("Consent requires speaker, reviewer, evidence file and expiry")
    expires = datetime.fromisoformat(data["expires_at"])
    if expires.tzinfo is None or expires <= datetime.now(UTC):
        raise ValueError("Voice consent is expired or missing a time zone")
    if not isinstance(data.get("languages"), list) or language not in data["languages"]:
        raise ValueError("Voice consent does not cover this language")
    checks = (
        (reference, "reference_sha256"),
        (movie, "reel_sha256"),
        (receipt.parent / data["evidence_file"], "evidence_sha256"),
    )
    if any(data.get(key) != file_digest(path) for path, key in checks):
        raise ValueError("Voice consent does not match the reference, reel or evidence")


def dub_reel(
    movie: Path,
    subtitles: Path,
    language: str,
    *,
    worker: Path,
    weights: Path,
    reference: Path | None = None,
    consent: Path | None = None,
) -> Path:
    if language not in ("en", "ar"):
        raise ValueError("Choose ar or en")
    if (reference is None) != (consent is None):
        raise ValueError("Cloning requires a reference recording and its consent receipt")
    binary = find_ffmpeg()
    if binary is None:
        raise ValueError("FFmpeg is required for dubbing")
    duration = probe_duration_ms(movie, binary)
    txt = subtitles.read_text(encoding="utf-8-sig").strip()
    times = parse_srt_times(txt)
    phrases = [" ".join(b.splitlines()[2:]).strip() for b in txt.split("\n\n")]
    if not times or len(phrases) != len(times) or not all(phrases) or times[-1][1] > duration:
        raise ValueError("Dub subtitles must cover speech within the rendered video")
    if any(a[1] > b[0] for a, b in pairwise(times)):
        raise ValueError("Overlapping dub cues")
    output = movie.with_suffix(f".{language}.dub.mp4")
    with tempfile.TemporaryDirectory(dir=movie.parent) as working:
        stage = Path(working)
        ref_path = None
        if reference is not None and consent is not None:
            ref_path = stage / "reference.wav"
            shutil.copyfile(reference, ref_path)
            verify_voice_consent(consent, ref_path, movie, language)
        request = stage / "speech.json"
        request.write_text(
            json.dumps(
                {
                    "phrases": phrases,
                    "weights": str(weights.resolve()),
                    "language": language,
                    "reference": str(ref_path.resolve()) if ref_path else None,
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [str(worker), "-I", str(Path(__file__).with_name("voice_worker.py")), str(request)],
            check=True,
            timeout=300 + 180 * len(phrases),
        )
        cmd = [str(binary), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(movie)]
        filters = []
        labels = []
        for index, (start, end) in enumerate(times):
            wav = stage / f"cue-{index}.wav"
            with wave.open(str(wav), "rb") as cue:
                length = cue.getnframes() / cue.getframerate()
            factor = max(1.0, length * 1000 / (end - start))
            cmd.extend(["-i", str(wav)])
            label = f"v{index}"
            filters.append(
                f"[{index + 1}:a]atempo={factor:.6f},atrim=duration={(end - start) / 1000:.3f},"
                f"adelay={start}:all=1[{label}]"
            )
            labels.append(f"[{label}]")
        filters.append("".join(labels) + f"amix=inputs={len(times)}:normalize=0,apad[dub]")
        staged = stage / "dub.mp4"
        lang = "eng" if language == "en" else "ara"
        cmd.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "0:v:0",
                "-map",
                "[dub]",
                "-map",
                "0:a:0",
                "-c:v",
                "copy",
                "-c:a:0",
                "aac",
                "-b:a:0",
                "192k",
                "-c:a:1",
                "copy",
                "-metadata:s:a:0",
                "language=" + lang,
                "-metadata:s:a:1",
                "language=ckb",
                "-disposition:a:0",
                "default",
                "-disposition:a:1",
                "0",
                "-t",
                f"{duration / 1000:.3f}",
                "-movflags",
                "+faststart",
                str(staged),
            ]
        )
        subprocess.run(cmd, check=True, timeout=600)
        staged.replace(output)
    return output


def dub_cli(argv: list[str]) -> int:
    parser = ArgumentParser(prog="hawedit.v8 dub")
    parser.add_argument("movie", type=Path)
    parser.add_argument("subtitles", type=Path)
    parser.add_argument("--language", required=True, choices=("ar", "en"))
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--voice-python", required=True, type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--consent", type=Path)
    args = parser.parse_args(argv)
    print(
        dub_reel(
            args.movie,
            args.subtitles,
            args.language,
            worker=args.voice_python,
            weights=args.weights,
            reference=args.reference,
            consent=args.consent,
        )
    )
    return 0
