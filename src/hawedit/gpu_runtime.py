"""Fail-closed runtime identity for HawEdit's measured dual-3090-Ti CUDA host."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

__all__ = [
    "GpuDeviceReport",
    "GpuRuntimeError",
    "GpuRuntimeReport",
    "audit_gpu_runtime",
    "main",
]

_TORCH_VERSION: Final = "2.13.0+cu130"
_TORCHVISION_VERSION: Final = "0.28.0+cu130"
_TORCHAUDIO_VERSION: Final = "2.11.0+cu130"
_CUDA_VERSION: Final = "13.0"
_CUDNN_VERSION: Final = 92000
_DEVICE_NAME: Final = "NVIDIA GeForce RTX 3090 Ti"
_COMPUTE_CAPABILITY: Final = (8, 6)
_MINIMUM_MEMORY_BYTES: Final = 23 * 1024**3
_VISIBILITY_VARIABLES: Final = ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES")


class GpuRuntimeError(RuntimeError):
    """The active process is not the measured HawEdit CUDA deployment."""


@dataclass(frozen=True, slots=True)
class GpuDeviceReport:
    index: int
    name: str
    compute_capability: tuple[int, int]
    total_memory_bytes: int


@dataclass(frozen=True, slots=True)
class GpuRuntimeReport:
    torch_version: str
    torchvision_version: str
    torchaudio_version: str
    cuda_version: str
    cudnn_version: int
    devices: tuple[GpuDeviceReport, ...]


def _version(module: Any, name: str) -> str:
    value = getattr(module, "__version__", None)
    if not isinstance(value, str):
        raise GpuRuntimeError(f"{name} has no string runtime version")
    return value


def _audit_modules(torch: Any, torchvision: Any, torchaudio: Any) -> GpuRuntimeReport:
    torch_version = _version(torch, "torch")
    torchvision_version = _version(torchvision, "torchvision")
    torchaudio_version = _version(torchaudio, "torchaudio")
    if torch_version != _TORCH_VERSION:
        raise GpuRuntimeError(f"torch runtime is {torch_version}, expected {_TORCH_VERSION}")
    if torchvision_version != _TORCHVISION_VERSION:
        raise GpuRuntimeError(
            f"torchvision runtime is {torchvision_version}, expected {_TORCHVISION_VERSION}"
        )
    if torchaudio_version != _TORCHAUDIO_VERSION:
        raise GpuRuntimeError(
            f"torchaudio runtime is {torchaudio_version}, expected {_TORCHAUDIO_VERSION}"
        )

    cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
    if cuda_version != _CUDA_VERSION:
        raise GpuRuntimeError(f"torch CUDA runtime is {cuda_version!r}, expected {_CUDA_VERSION}")
    try:
        cudnn_version = torch.backends.cudnn.version()
    except (AttributeError, RuntimeError) as exc:
        raise GpuRuntimeError(f"cannot query cuDNN runtime: {exc}") from exc
    if cudnn_version != _CUDNN_VERSION:
        raise GpuRuntimeError(f"cuDNN runtime is {cudnn_version!r}, expected {_CUDNN_VERSION}")
    try:
        available = torch.cuda.is_available()
        count = torch.cuda.device_count()
    except (AttributeError, RuntimeError) as exc:
        raise GpuRuntimeError(f"cannot query CUDA devices: {exc}") from exc
    if available is not True:
        raise GpuRuntimeError("torch reports CUDA unavailable")
    if count != 2:
        raise GpuRuntimeError(f"measured deployment requires exactly 2 CUDA devices, found {count}")

    devices: list[GpuDeviceReport] = []
    for index in range(count):
        try:
            name = torch.cuda.get_device_name(index)
            capability = tuple(torch.cuda.get_device_capability(index))
            properties = torch.cuda.get_device_properties(index)
            total_memory = properties.total_memory
        except (AttributeError, RuntimeError, TypeError) as exc:
            raise GpuRuntimeError(f"cannot inspect CUDA device {index}: {exc}") from exc
        if name != _DEVICE_NAME:
            raise GpuRuntimeError(f"CUDA device {index} is {name!r}, expected {_DEVICE_NAME!r}")
        if capability != _COMPUTE_CAPABILITY:
            raise GpuRuntimeError(
                f"CUDA device {index} has compute capability {capability}, "
                f"expected {_COMPUTE_CAPABILITY}"
            )
        if not isinstance(total_memory, int) or total_memory < _MINIMUM_MEMORY_BYTES:
            raise GpuRuntimeError(
                f"CUDA device {index} exposes {total_memory!r} bytes, expected at least "
                f"{_MINIMUM_MEMORY_BYTES}"
            )
        try:
            left = torch.ones((16, 16), device=f"cuda:{index}", dtype=torch.bfloat16)
            result = left @ left
            checksum = float(result.float().sum().item())
            torch.cuda.synchronize(index)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            raise GpuRuntimeError(f"CUDA device {index} bfloat16 compute failed: {exc}") from exc
        if checksum != 4096.0:
            raise GpuRuntimeError(
                f"CUDA device {index} bfloat16 compute returned checksum {checksum!r}"
            )
        devices.append(
            GpuDeviceReport(
                index=index,
                name=name,
                compute_capability=cast(tuple[int, int], capability),
                total_memory_bytes=total_memory,
            )
        )

    return GpuRuntimeReport(
        torch_version=torch_version,
        torchvision_version=torchvision_version,
        torchaudio_version=torchaudio_version,
        cuda_version=cuda_version,
        cudnn_version=cudnn_version,
        devices=tuple(devices),
    )


def audit_gpu_runtime() -> GpuRuntimeReport:
    """Prove the package runtime, visibility, identity and compute path used in production."""

    configured = [name for name in _VISIBILITY_VARIABLES if name in os.environ]
    if configured:
        raise GpuRuntimeError(
            "GPU visibility overrides are forbidden for the measured deployment: "
            + ", ".join(configured)
        )
    try:
        torch = importlib.import_module("torch")
        torchvision = importlib.import_module("torchvision")
        torchaudio = importlib.import_module("torchaudio")
    except ImportError as exc:
        raise GpuRuntimeError(f"CUDA runtime package is unavailable: {exc}") from exc
    return _audit_modules(torch, torchvision, torchaudio)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("REFUSED: hawedit.gpu_runtime accepts no arguments", file=sys.stderr)
        return 2
    try:
        report = audit_gpu_runtime()
    except GpuRuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    memory_gib = ",".join(f"{item.total_memory_bytes / 1024**3:.1f}" for item in report.devices)
    print(
        "hawedit-gpu-runtime-ok: "
        f"torch={report.torch_version} torchvision={report.torchvision_version} "
        f"torchaudio={report.torchaudio_version} cuda={report.cuda_version} "
        f"cudnn={report.cudnn_version} devices={len(report.devices)} memory_gib={memory_gib}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
