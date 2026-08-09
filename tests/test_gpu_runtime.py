"""The production GPU check must prove the measured stack instead of CUDA in general."""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from hawedit.gpu_runtime import GpuRuntimeError, _audit_modules, audit_gpu_runtime, main


class _Tensor:
    def __matmul__(self, _other: object) -> _Tensor:
        return self

    def float(self) -> _Tensor:
        return self

    def sum(self) -> _Tensor:
        return self

    def item(self) -> builtins.float:
        return 4096.0


class _Cuda:
    def __init__(self) -> None:
        self.available = True
        self.count = 2
        self.names = ["NVIDIA GeForce RTX 3090 Ti"] * 2
        self.capabilities = [(8, 6)] * 2
        self.memories = [24 * 1024**3] * 2
        self.synchronized: list[int] = []

    def is_available(self) -> bool:
        return self.available

    def device_count(self) -> int:
        return self.count

    def get_device_name(self, index: int) -> str:
        return self.names[index]

    def get_device_capability(self, index: int) -> tuple[int, int]:
        return self.capabilities[index]

    def get_device_properties(self, index: int) -> SimpleNamespace:
        return SimpleNamespace(total_memory=self.memories[index])

    def synchronize(self, index: int) -> None:
        self.synchronized.append(index)


class _Torch:
    def __init__(self) -> None:
        self.__version__ = "2.13.0+cu130"
        self.version = SimpleNamespace(cuda="13.0")
        self.backends = SimpleNamespace(cudnn=SimpleNamespace(version=lambda: 92000))
        self.cuda = _Cuda()
        self.bfloat16 = object()
        self.compute_error: Exception | None = None

    def ones(self, _shape: tuple[int, int], *, device: str, dtype: object) -> _Tensor:
        assert device in {"cuda:0", "cuda:1"}
        assert dtype is self.bfloat16
        if self.compute_error is not None:
            raise self.compute_error
        return _Tensor()


def _runtime() -> tuple[_Torch, SimpleNamespace, SimpleNamespace]:
    return (
        _Torch(),
        SimpleNamespace(__version__="0.28.0+cu130"),
        SimpleNamespace(__version__="2.11.0+cu130"),
    )


def test_measured_dual_3090_ti_runtime_is_accepted() -> None:
    torch, torchvision, torchaudio = _runtime()
    report = _audit_modules(torch, torchvision, torchaudio)
    assert report.torch_version == "2.13.0+cu130"
    assert report.cuda_version == "13.0"
    assert report.cudnn_version == 92000
    assert report.torchaudio_version == "2.11.0+cu130"
    assert [item.index for item in report.devices] == [0, 1]
    assert torch.cuda.synchronized == [0, 1]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("torch", "torch runtime"),
        ("torchvision", "torchvision runtime"),
        ("torchaudio", "torchaudio runtime"),
        ("cuda", "CUDA runtime"),
        ("cudnn", "cuDNN runtime"),
        ("unavailable", "CUDA unavailable"),
        ("count", "exactly 2 CUDA devices"),
        ("name", "expected 'NVIDIA GeForce RTX 3090 Ti'"),
        ("capability", "compute capability"),
        ("memory", "expected at least"),
        ("compute", "bfloat16 compute failed"),
    ],
)
def test_runtime_identity_or_compute_drift_is_refused(case: str, message: str) -> None:
    torch, torchvision, torchaudio = _runtime()
    if case == "torch":
        torch.__version__ = "2.13.0+cpu"
    elif case == "torchvision":
        torchvision.__version__ = "0.28.0+cpu"
    elif case == "torchaudio":
        torchaudio.__version__ = "2.11.0+cpu"
    elif case == "cuda":
        torch.version.cuda = "12.8"
    elif case == "cudnn":
        torch.backends.cudnn.version = lambda: 91000
    elif case == "unavailable":
        torch.cuda.available = False
    elif case == "count":
        torch.cuda.count = 1
    elif case == "name":
        torch.cuda.names[1] = "NVIDIA A100"
    elif case == "capability":
        torch.cuda.capabilities[1] = (8, 0)
    elif case == "memory":
        torch.cuda.memories[1] = 16 * 1024**3
    elif case == "compute":
        torch.compute_error = RuntimeError("kernel launch failed")
    with pytest.raises(GpuRuntimeError, match=message):
        _audit_modules(torch, torchvision, torchaudio)


@pytest.mark.parametrize("variable", ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"])
def test_visibility_overrides_are_refused_before_import(
    variable: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(variable, "0,1")
    with pytest.raises(GpuRuntimeError, match="visibility overrides"):
        audit_gpu_runtime()


def test_cli_refuses_arguments_and_normalizes_runtime_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["unexpected"]) == 2
    monkeypatch.setattr(
        "hawedit.gpu_runtime.audit_gpu_runtime",
        lambda: (_ for _ in ()).throw(GpuRuntimeError("driver refused")),
    )
    assert main([]) == 3
    assert "REFUSED: driver refused" in capsys.readouterr().err
