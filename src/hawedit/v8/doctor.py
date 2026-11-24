"""HawEdit V9 Team Preflight Diagnostic ``doctor`` (D-391).

Fast (< 3 s), read-only subsystem preflight checks returning both structured JSON
(``DoctorReport.to_dict()``) and a clean CLI checklist (``format_doctor_report``):

1. ``gpu_nvenc``: queries ``nvidia-smi`` + FFmpeg ``h264_nvenc`` probe.
2. ``ffmpeg_rtl``: locates FFmpeg via ``find_ffmpeg()`` + ``assert_rtl_stack``.
3. ``skia_harfbuzz``: verifies ``skia`` + ``uharfbuzz`` imports + Vazirmatn Kurdish coverage.
4. ``wsl_asr``: probes ``127.0.0.1:8000/health`` and ``127.0.0.1:8001/health`` (2 s timeout).
5. ``gemini_director``: checks ``GEMINI_API_KEY`` presence (never prints or returns secret).
6. ``local_omni_director``: probes ``HAWEDIT_OMNI_URL`` / ``127.0.0.1:1234/v1/models``.
7. ``disk_space``: verifies free GB on work/output drive (warns if ``< 10 GB``).

Stdlib + existing HawEdit modules only; zero silent fallbacks; zero side effects.
"""

from __future__ import annotations

import concurrent.futures
import importlib
import json
import math
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from hawedit.captions import (
    FontCoverageError,
    MissingRtlStack,
    _default_fonts_dir,
    assert_font_covers_kurdish,
    assert_rtl_stack,
    find_ffmpeg,
)
from hawedit.credentials import GEMINI_API_KEY, read_credential
from hawedit.http_transport import open_without_redirects
from hawedit.render import Encoder, encoder_available, linked_libraries
from hawedit.v8.director import DEFAULT_OMNI_URL, OMNI_URL_ENV

__all__ = [
    "CORE_PRODUCTION_CHECKS",
    "DEFAULT_HTTP_TIMEOUT_S",
    "DEFAULT_MIN_DISK_GB",
    "DEFAULT_WSL_ASR_URLS",
    "DoctorCheck",
    "DoctorReport",
    "DoctorStatus",
    "format_doctor_report",
    "run_v8_doctor",
]

DoctorStatus = Literal["ok", "warn", "fail"]

DEFAULT_WSL_ASR_URLS: Final[tuple[str, ...]] = (
    "http://127.0.0.1:8000/health",
    "http://127.0.0.1:8001/health",
)
DEFAULT_MIN_DISK_GB: Final[float] = 10.0
DEFAULT_HTTP_TIMEOUT_S: Final[float] = 2.0
CORE_PRODUCTION_CHECKS: Final[tuple[str, ...]] = (
    "ffmpeg_rtl",
    "skia_harfbuzz",
    "disk_space",
)

_MAX_PROBE_BYTES: Final[int] = 64 * 1024
_SUBPROCESS_TIMEOUT_S: Final[float] = 2.0
_GIB: Final[float] = float(1024**3)
_VAZIRMATN_CANDIDATES: Final[tuple[str, ...]] = (
    "Vazirmatn-ExtraBold.ttf",
    "Vazirmatn.ttf",
)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """Single read-only subsystem preflight probe result."""

    name: str
    status: DoctorStatus
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("DoctorCheck.name must be non-empty")
        if self.status not in ("ok", "warn", "fail"):
            raise ValueError(f"Invalid DoctorCheck.status: {self.status!r}")
        if not math.isfinite(self.elapsed_ms) or self.elapsed_ms < 0.0:
            raise ValueError(f"DoctorCheck.elapsed_ms must be finite >= 0, got {self.elapsed_ms!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this check to a JSON-safe dictionary."""
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "details": dict(self.details),
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Aggregated V8/V9 team preflight report."""

    checks: tuple[DoctorCheck, ...]
    ready_for_production: bool
    elapsed_ms: float
    gpu_note: str

    def get(self, name: str) -> DoctorCheck | None:
        """Look up a check by its canonical name."""
        for check in self.checks:
            if check.name == name:
                return check
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full doctor report to structured JSON."""
        checks_list = [c.to_dict() for c in self.checks]
        return {
            "ready_for_production": self.ready_for_production,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "gpu_note": self.gpu_note,
            "counts": {
                "ok": sum(1 for c in self.checks if c.status == "ok"),
                "warn": sum(1 for c in self.checks if c.status == "warn"),
                "fail": sum(1 for c in self.checks if c.status == "fail"),
            },
            "checks": checks_list,
            "checks_by_name": {c.name: c.to_dict() for c in self.checks},
        }


def _bounded_text(raw: str, limit: int = 200) -> str:
    printable = "".join(ch if ch.isprintable() else " " for ch in raw)
    collapsed = " ".join(printable.split())
    if len(collapsed) > limit:
        return f"{collapsed[: limit - 3]}..."
    return collapsed


def _normalize_models_url(raw_url: str) -> str:
    clean = raw_url.strip().rstrip("/")
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid Omni URL: {raw_url!r}")
    if clean.endswith("/models"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/models"
    return f"{clean}/v1/models"


def _probe_http_json(
    url: str, *, timeout_s: float
) -> tuple[int, dict[str, Any] | None, str | None]:
    """Perform a read-only GET probe with redirect refusal and bounded body read."""
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with open_without_redirects(req, timeout=timeout_s) as resp:
            status = int(resp.status)
            raw = resp.read(_MAX_PROBE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return int(exc.code), None, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, None, _bounded_text(str(exc))

    text = raw[:_MAX_PROBE_BYTES].decode("utf-8", errors="replace")
    if status != 200:
        return status, None, f"HTTP {status}: {_bounded_text(text)}"
    try:
        decoded: object = json.loads(text)
    except ValueError as exc:
        return status, None, f"invalid JSON: {exc}"
    if not isinstance(decoded, dict):
        return status, None, f"expected JSON object, got {type(decoded).__name__}"
    return status, decoded, None


def _query_nvidia_smi(
    *, timeout_s: float = _SUBPROCESS_TIMEOUT_S
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Query NVIDIA GPU names and total/free MiB via ``nvidia-smi``."""
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return False, [], "nvidia-smi not found on PATH"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, [], _bounded_text(str(exc))

    if proc.returncode != 0:
        detail = _bounded_text(proc.stderr or proc.stdout)
        return False, [], f"nvidia-smi exited {proc.returncode}: {detail}"

    gpus: list[dict[str, Any]] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            idx = int(parts[0])
            name = parts[1]
            total_mib = int(float(parts[2]))
            free_mib = int(float(parts[3]))
        except ValueError:
            continue
        gpus.append(
            {
                "index": idx,
                "name": name,
                "memory_total_mib": total_mib,
                "memory_free_mib": free_mib,
            }
        )
    return True, gpus, None


def _run_ffmpeg_buildconf(
    binary: Path, *, timeout_s: float = _SUBPROCESS_TIMEOUT_S
) -> tuple[bool, str, str]:
    """Return ``(ok, buildconf_output, linked_libs_output)`` for ``binary``."""
    try:
        proc = subprocess.run(
            [str(binary), "-hide_banner", "-buildconf"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc), ""
    if proc.returncode != 0:
        return False, _bounded_text(proc.stderr or proc.stdout), ""
    linked = linked_libraries(binary) if platform.system() == "Linux" else ""
    return True, proc.stdout + proc.stderr, linked


def _import_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _check_gpu_nvenc(ffmpeg_bin: Path | None) -> tuple[DoctorCheck, str]:
    t0 = time.perf_counter()
    smi_ok, gpus, smi_err = _query_nvidia_smi()
    nvenc_ok = False
    if ffmpeg_bin is not None and ffmpeg_bin.is_file():
        nvenc_ok = encoder_available(Encoder.NVENC, ffmpeg_bin)

    elapsed = (time.perf_counter() - t0) * 1000.0
    if nvenc_ok and gpus:
        gpu_desc = "; ".join(
            f"GPU {g['index']}: {g['name']} "
            f"({g['memory_free_mib']}/{g['memory_total_mib']} MiB free)"
            for g in gpus
        )
        plural = "GPU" if len(gpus) == 1 else "GPUs"
        gpu_note = f"NVENC ready on {gpus[0]['name']} ({len(gpus)} {plural})"
        return (
            DoctorCheck(
                name="gpu_nvenc",
                status="ok",
                summary=f"h264_nvenc ready - {gpu_desc}",
                details={
                    "gpus": gpus,
                    "nvenc_available": True,
                    "nvidia_smi_ok": True,
                    "cpu_fallback_note": "hardware NVENC active",
                },
                elapsed_ms=elapsed,
            ),
            gpu_note,
        )
    if nvenc_ok:
        gpu_note = "NVENC ready (nvidia-smi unavailable)"
        return (
            DoctorCheck(
                name="gpu_nvenc",
                status="ok",
                summary="h264_nvenc ready (nvidia-smi unavailable)",
                details={
                    "gpus": [],
                    "nvenc_available": True,
                    "nvidia_smi_ok": False,
                    "nvidia_smi_error": smi_err,
                    "cpu_fallback_note": "hardware NVENC active",
                },
                elapsed_ms=elapsed,
            ),
            gpu_note,
        )

    if gpus:
        reason = "FFmpeg missing" if ffmpeg_bin is None else "FFmpeg h264_nvenc probe failed"
        gpu_note = f"GPU detected ({gpus[0]['name']}) but {reason} - explicit CPU libx264 required"
        return (
            DoctorCheck(
                name="gpu_nvenc",
                status="warn",
                summary=(
                    f"GPU detected ({len(gpus)}) but {reason}; explicit --encoder libx264 required"
                ),
                details={
                    "gpus": gpus,
                    "nvenc_available": False,
                    "nvidia_smi_ok": smi_ok,
                    "cpu_fallback_note": gpu_note,
                },
                elapsed_ms=elapsed,
            ),
            gpu_note,
        )

    gpu_note = "No NVIDIA GPU / h264_nvenc unavailable - explicit CPU libx264 required"
    return (
        DoctorCheck(
            name="gpu_nvenc",
            status="warn",
            summary=(
                f"No NVIDIA GPU or h264_nvenc available ({smi_err or 'CPU only'}); "
                "explicit --encoder libx264 required"
            ),
            details={
                "gpus": [],
                "nvenc_available": False,
                "nvidia_smi_ok": smi_ok,
                "nvidia_smi_error": smi_err,
                "cpu_fallback_note": gpu_note,
            },
            elapsed_ms=elapsed,
        ),
        gpu_note,
    )


def _check_ffmpeg_rtl(ffmpeg_bin: Path | None) -> DoctorCheck:
    t0 = time.perf_counter()
    if ffmpeg_bin is None or not ffmpeg_bin.is_file():
        return DoctorCheck(
            name="ffmpeg_rtl",
            status="fail",
            summary=(
                "FFmpeg binary not found; run bash scripts/fetch-ffmpeg.sh or set HAWEDIT_FFMPEG"
            ),
            details={"ffmpeg_path": str(ffmpeg_bin) if ffmpeg_bin is not None else None},
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    ok, buildconf, linked = _run_ffmpeg_buildconf(ffmpeg_bin)
    if not ok:
        return DoctorCheck(
            name="ffmpeg_rtl",
            status="fail",
            summary=f"FFmpeg at {ffmpeg_bin} failed -buildconf: {buildconf}",
            details={"ffmpeg_path": str(ffmpeg_bin), "error": buildconf},
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    try:
        report = assert_rtl_stack(buildconf, linked)
    except MissingRtlStack as exc:
        return DoctorCheck(
            name="ffmpeg_rtl",
            status="fail",
            summary=f"FFmpeg missing Kurdish RTL stack: {_bounded_text(str(exc))}",
            details={"ffmpeg_path": str(ffmpeg_bin), "error": str(exc)},
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    return DoctorCheck(
        name="ffmpeg_rtl",
        status="ok",
        summary=f"FFmpeg RTL stack verified (libass + HarfBuzz + FriBidi) at {ffmpeg_bin.name}",
        details={
            "ffmpeg_path": str(ffmpeg_bin),
            "libass": report.libass,
            "harfbuzz": report.harfbuzz,
            "fribidi": report.fribidi,
            "harfbuzz_source": report.harfbuzz_source,
            "fribidi_source": report.fribidi_source,
        },
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
    )


def _resolve_vazirmatn_font(fonts_dir: Path) -> Path | None:
    for filename in _VAZIRMATN_CANDIDATES:
        candidate = fonts_dir / filename
        if candidate.is_file():
            return candidate
    return None


def _check_skia_harfbuzz(fonts_dir: Path | None) -> DoctorCheck:
    t0 = time.perf_counter()
    skia_ok = False
    skia_ver: str | None = None
    hb_ok = False
    hb_ver: str | None = None
    import_errors: list[str] = []

    try:
        skia_mod = _import_module("skia")
        skia_ok = True
        raw_ver = getattr(skia_mod, "__version__", None)
        skia_ver = str(raw_ver) if raw_ver is not None else None
    except Exception as exc:
        import_errors.append(f"skia: {_bounded_text(str(exc))}")

    try:
        hb_mod = _import_module("uharfbuzz")
        hb_ok = True
        raw_hb = getattr(hb_mod, "__version__", None)
        hb_ver = str(raw_hb) if raw_hb is not None else None
    except Exception as exc:
        import_errors.append(f"uharfbuzz: {_bounded_text(str(exc))}")

    resolved_fonts_dir = fonts_dir if fonts_dir is not None else _default_fonts_dir()
    font_path = _resolve_vazirmatn_font(resolved_fonts_dir)

    if not skia_ok or not hb_ok:
        return DoctorCheck(
            name="skia_harfbuzz",
            status="fail",
            summary=f"Missing Skia/HarfBuzz runtime: {'; '.join(import_errors)}",
            details={
                "skia_available": skia_ok,
                "skia_version": skia_ver,
                "uharfbuzz_available": hb_ok,
                "uharfbuzz_version": hb_ver,
                "font_path": str(font_path) if font_path is not None else None,
                "kurdish_coverage": False,
                "errors": import_errors,
            },
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    if font_path is None:
        expected = ", ".join(str(resolved_fonts_dir / f) for f in _VAZIRMATN_CANDIDATES)
        return DoctorCheck(
            name="skia_harfbuzz",
            status="fail",
            summary=f"Vazirmatn font missing in {resolved_fonts_dir}",
            details={
                "skia_available": True,
                "skia_version": skia_ver,
                "uharfbuzz_available": True,
                "uharfbuzz_version": hb_ver,
                "font_path": None,
                "expected_candidates": expected,
                "kurdish_coverage": False,
            },
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    try:
        assert_font_covers_kurdish(font_path)
    except (FontCoverageError, OSError, ValueError) as exc:
        return DoctorCheck(
            name="skia_harfbuzz",
            status="fail",
            summary=(
                f"Font {font_path.name} failed Kurdish glyph coverage: {_bounded_text(str(exc))}"
            ),
            details={
                "skia_available": True,
                "skia_version": skia_ver,
                "uharfbuzz_available": True,
                "uharfbuzz_version": hb_ver,
                "font_path": str(font_path),
                "kurdish_coverage": False,
                "error": str(exc),
            },
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    return DoctorCheck(
        name="skia_harfbuzz",
        status="ok",
        summary=(
            f"skia {skia_ver or 'ok'} + uharfbuzz {hb_ver or 'ok'} ready; "
            f"{font_path.name} covers Sorani Kurdish"
        ),
        details={
            "skia_available": True,
            "skia_version": skia_ver,
            "uharfbuzz_available": True,
            "uharfbuzz_version": hb_ver,
            "font_path": str(font_path),
            "kurdish_coverage": True,
        },
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
    )


def _check_wsl_asr(
    urls: Sequence[str],
    *,
    timeout_s: float,
) -> DoctorCheck:
    t0 = time.perf_counter()
    if not urls:
        return DoctorCheck(
            name="wsl_asr",
            status="warn",
            summary="No WSL ASR health endpoints configured",
            details={"endpoints": [], "healthy_count": 0, "total_count": 0},
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def _probe_one(url: str) -> dict[str, Any]:
        status, body, err = _probe_http_json(url, timeout_s=timeout_s)
        ok = status == 200 and body is not None
        return {
            "url": url,
            "ok": ok,
            "http_status": status,
            "status": body.get("status") if isinstance(body, Mapping) else None,
            "model": body.get("model") if isinstance(body, Mapping) else None,
            "device": body.get("device") if isinstance(body, Mapping) else None,
            "vram_allocated_gb": body.get("vram_allocated_gb")
            if isinstance(body, Mapping)
            else None,
            "error": err,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as pool:
        endpoints = list(pool.map(_probe_one, urls))

    healthy = [ep for ep in endpoints if ep["ok"]]
    elapsed = (time.perf_counter() - t0) * 1000.0
    details = {
        "endpoints": endpoints,
        "healthy_count": len(healthy),
        "total_count": len(endpoints),
    }

    if len(healthy) == len(endpoints):
        models = sorted({str(ep["model"]) for ep in healthy if ep.get("model")})
        model_note = f" ({', '.join(models)})" if models else ""
        return DoctorCheck(
            name="wsl_asr",
            status="ok",
            summary=f"WSL ASR healthy on {len(healthy)}/{len(endpoints)} endpoints{model_note}",
            details=details,
            elapsed_ms=elapsed,
        )

    if healthy:
        up_urls = ", ".join(str(ep["url"]) for ep in healthy)
        return DoctorCheck(
            name="wsl_asr",
            status="warn",
            summary=f"WSL ASR partially healthy ({len(healthy)}/{len(endpoints)} up: {up_urls})",
            details=details,
            elapsed_ms=elapsed,
        )

    return DoctorCheck(
        name="wsl_asr",
        status="warn",
        summary=(
            f"WSL ASR unreachable on 0/{len(endpoints)} endpoints "
            "(existing transcripts still usable)"
        ),
        details=details,
        elapsed_ms=elapsed,
    )


def _check_gemini_director() -> DoctorCheck:
    t0 = time.perf_counter()
    try:
        secret = read_credential(GEMINI_API_KEY)
    except (OSError, UnicodeError) as exc:
        return DoctorCheck(
            name="gemini_director",
            status="warn",
            summary=f"{GEMINI_API_KEY} credential store unreadable: {_bounded_text(str(exc))}",
            details={
                "configured": False,
                "credential_name": GEMINI_API_KEY,
                "error": _bounded_text(str(exc)),
            },
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    configured = bool(secret and secret.strip())
    elapsed = (time.perf_counter() - t0) * 1000.0
    if configured:
        return DoctorCheck(
            name="gemini_director",
            status="ok",
            summary=f"{GEMINI_API_KEY} configured (secret redacted)",
            details={"configured": True, "credential_name": GEMINI_API_KEY},
            elapsed_ms=elapsed,
        )
    return DoctorCheck(
        name="gemini_director",
        status="warn",
        summary=f"{GEMINI_API_KEY} not configured (cloud Gemini director unavailable)",
        details={"configured": False, "credential_name": GEMINI_API_KEY},
        elapsed_ms=elapsed,
    )


def _check_local_omni_director(
    omni_url: str | None,
    *,
    timeout_s: float,
) -> DoctorCheck:
    t0 = time.perf_counter()
    raw_url = (
        (os.environ.get(OMNI_URL_ENV, "").strip() or DEFAULT_OMNI_URL)
        if omni_url is None
        else omni_url.strip()
    )
    try:
        models_url = _normalize_models_url(raw_url)
    except ValueError as exc:
        return DoctorCheck(
            name="local_omni_director",
            status="warn",
            summary=f"Invalid local Omni URL: {_bounded_text(str(exc))}",
            details={
                "url": raw_url,
                "reachable": False,
                "http_status": 0,
                "models": [],
                "embedding_models_filtered": 0,
                "error": str(exc),
            },
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    status, body, err = _probe_http_json(models_url, timeout_s=timeout_s)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if status != 200 or body is None:
        return DoctorCheck(
            name="local_omni_director",
            status="warn",
            summary=(
                f"Local Omni/LM Studio server unreachable at {models_url} "
                f"({err or f'HTTP {status}'})"
            ),
            details={
                "url": models_url,
                "reachable": False,
                "http_status": status,
                "models": [],
                "embedding_models_filtered": 0,
                "error": err,
            },
            elapsed_ms=elapsed,
        )

    raw_models = body.get("data")
    if not isinstance(raw_models, list):
        return DoctorCheck(
            name="local_omni_director",
            status="warn",
            summary=f"Local server at {models_url} returned /models without 'data' list",
            details={
                "url": models_url,
                "reachable": True,
                "http_status": status,
                "models": [],
                "embedding_models_filtered": 0,
                "error": "missing data list",
            },
            elapsed_ms=elapsed,
        )

    models: list[str] = []
    embed_count = 0
    for item in raw_models:
        if not isinstance(item, Mapping):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        clean_id = mid.strip()
        if "embed" in clean_id.lower():
            embed_count += 1
        else:
            models.append(clean_id)

    details = {
        "url": models_url,
        "reachable": True,
        "http_status": status,
        "models": models,
        "embedding_models_filtered": embed_count,
        "error": None,
    }
    if not models:
        return DoctorCheck(
            name="local_omni_director",
            status="warn",
            summary=f"Local server reachable at {models_url} but 0 non-embedding models loaded",
            details=details,
            elapsed_ms=elapsed,
        )

    preview = ", ".join(models[:4])
    suffix = f" (+{len(models) - 4} more)" if len(models) > 4 else ""
    return DoctorCheck(
        name="local_omni_director",
        status="ok",
        summary=f"Local LLM ready at {models_url} ({len(models)} model(s): {preview}{suffix})",
        details=details,
        elapsed_ms=elapsed,
    )


def _resolve_existing_dir(work_dir: Path | None) -> Path:
    if work_dir is None:
        return Path.cwd()
    candidate = work_dir.expanduser()
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate if candidate.exists() else Path.cwd()


def _check_disk_space(work_dir: Path | None, *, min_disk_gb: float) -> DoctorCheck:
    t0 = time.perf_counter()
    target = _resolve_existing_dir(work_dir)
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return DoctorCheck(
            name="disk_space",
            status="fail",
            summary=f"Unable to read disk space for {target}: {_bounded_text(str(exc))}",
            details={"path": str(target), "min_free_gb": min_disk_gb, "error": str(exc)},
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    free_gb = usage.free / _GIB
    total_gb = usage.total / _GIB
    used_gb = usage.used / _GIB
    elapsed = (time.perf_counter() - t0) * 1000.0
    details = {
        "path": str(target),
        "free_gb": round(free_gb, 2),
        "total_gb": round(total_gb, 2),
        "used_gb": round(used_gb, 2),
        "min_free_gb": min_disk_gb,
    }
    if free_gb < min_disk_gb:
        return DoctorCheck(
            name="disk_space",
            status="warn",
            summary=f"Low disk space: {free_gb:.1f} GB free on {target} (< {min_disk_gb:.1f} GB)",
            details=details,
            elapsed_ms=elapsed,
        )
    return DoctorCheck(
        name="disk_space",
        status="ok",
        summary=f"{free_gb:.1f} GB free / {total_gb:.1f} GB total on {target}",
        details=details,
        elapsed_ms=elapsed,
    )


def run_v8_doctor(
    *,
    work_dir: Path | None = None,
    ffmpeg: Path | None = None,
    fonts_dir: Path | None = None,
    omni_url: str | None = None,
    wsl_asr_urls: Sequence[str] = DEFAULT_WSL_ASR_URLS,
    min_disk_gb: float = DEFAULT_MIN_DISK_GB,
    http_timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> DoctorReport:
    """Run all 7 read-only V8/V9 team preflight probes in parallel (< 3 s)."""
    if not math.isfinite(min_disk_gb) or min_disk_gb <= 0.0:
        raise ValueError(f"min_disk_gb must be positive finite, got {min_disk_gb!r}")
    if not math.isfinite(http_timeout_s) or http_timeout_s <= 0.0:
        raise ValueError(f"http_timeout_s must be positive finite, got {http_timeout_s!r}")

    t_start = time.perf_counter()
    resolved_ffmpeg = ffmpeg if ffmpeg is not None else find_ffmpeg()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fut_gpu = pool.submit(_check_gpu_nvenc, resolved_ffmpeg)
        fut_ffmpeg = pool.submit(_check_ffmpeg_rtl, resolved_ffmpeg)
        fut_skia = pool.submit(_check_skia_harfbuzz, fonts_dir)
        fut_asr = pool.submit(_check_wsl_asr, tuple(wsl_asr_urls), timeout_s=http_timeout_s)
        fut_gemini = pool.submit(_check_gemini_director)
        fut_omni = pool.submit(_check_local_omni_director, omni_url, timeout_s=http_timeout_s)
        fut_disk = pool.submit(_check_disk_space, work_dir, min_disk_gb=min_disk_gb)

        gpu_check, gpu_note = fut_gpu.result()
        checks = (
            gpu_check,
            fut_ffmpeg.result(),
            fut_skia.result(),
            fut_asr.result(),
            fut_gemini.result(),
            fut_omni.result(),
            fut_disk.result(),
        )

    by_name = {c.name: c for c in checks}
    ready = all(by_name[name].status == "ok" for name in CORE_PRODUCTION_CHECKS)
    total_ms = (time.perf_counter() - t_start) * 1000.0
    return DoctorReport(
        checks=checks,
        ready_for_production=ready,
        elapsed_ms=total_ms,
        gpu_note=gpu_note,
    )


def format_doctor_report(report: DoctorReport) -> str:
    """Render a clean, ASCII-safe CLI preflight checklist."""
    tags: dict[DoctorStatus, str] = {
        "ok": "[OK]  ",
        "warn": "[WARN]",
        "fail": "[FAIL]",
    }
    verdict = "READY FOR PRODUCTION" if report.ready_for_production else "NOT READY FOR PRODUCTION"
    lines = [
        f"HawEdit V8/V9 Preflight Doctor - {verdict} ({report.elapsed_ms:.0f} ms)",
        f"GPU/Encoder: {report.gpu_note}",
        "-" * 76,
    ]
    for check in report.checks:
        lines.append(
            f"{tags[check.status]} {check.name:<20} {check.summary} ({check.elapsed_ms:.0f} ms)"
        )
    lines.append("-" * 76)
    counts = report.to_dict()["counts"]
    lines.append(
        f"Summary: {counts['ok']} ok, {counts['warn']} warn, {counts['fail']} fail | "
        f"ready_for_production={report.ready_for_production}"
    )
    return "\n".join(lines)
