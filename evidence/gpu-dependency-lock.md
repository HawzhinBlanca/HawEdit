# The measured Windows CUDA host now installs from one exact wheel graph

> Measured 2026-08-09 on Windows, CPython 3.11.15, two NVIDIA GeForce RTX
> 3090 Ti cards (24,564 MiB each), and NVIDIA driver 596.36.

## Reproducibility boundary

`requirements/host-gpu-windows-py311.txt` is the only GPU target. It binds the
`media,gpu` dependency graph to 46 exact Windows `win_amd64`/universal wheels,
one SHA-256 per selected artifact, with:

```
scope: gpu
target-platform: windows
target-python: 3.11
torch-backend: cu130
resolver: uv==0.11.26
exclude-newer: 2026-08-09T00:00:00Z
contract-sha256: ba1e7e0a5cd8e4f41d80b90c239b50e177798ae137724ebb3b61610451e91aea
```

Installation is fail-closed under `--require-hashes --only-binary`; the lock
uses the CUDA 13.0 PyTorch index as primary and PyPI as the explicit extra
index. The selected `torchvision` PEP 751 record did not publish a hash. The
generator therefore streamed that exact HTTPS wheel from the approved official
PyTorch artifact host, refused cross-host redirects and downloads over 1 GiB,
and committed the measured SHA-256
`0c6921bb5e3e58d926f80ff894739c8b9b0e72fed59a062e19c934f13dfd53ea`.
It refuses the same missing-hash condition for any non-PyTorch host.

`scripts/lock_host_dependencies.py --check` re-resolved all 13 host targets and
reported `host locks verified: 13 targets`; the GPU target resolved 46 packages.
The raw bytes of every lock, including this one, are bound in
`hawedit.host_lock_hashes`, so editing a requirement or hash without regenerating
the trusted digest is refused. The GPU lock is also wheel data and a required
release-wheel member, not a checkout-only file.

## Fresh exact install and installed-wheel proof

The fresh environment was created at `C:\hg-144447` and installed with:

```
bash scripts/install-host.sh C:/hg-144447/Scripts/python.exe gpu
```

The installer installed all 46 artifacts from hashes, `pip check` passed, the
exact installed inventory audit passed, and the hardware smoke reported:

```
hawedit-gpu-runtime-ok: torch=2.13.0+cu130 torchvision=0.28.0+cu130 torchaudio=2.11.0+cu130 cuda=13.0 cudnn=92000 devices=2 memory_gib=24.0,24.0
```

The smoke imports all three native packages and performs a bfloat16 matrix
multiply on each card. It also refuses a hidden device mask, any device count
other than two, a non-3090-Ti name, a compute capability other than 8.6, less
than 23 GiB per card, or version/CUDA/cuDNN drift.

To exercise the wheel-only operator path, a local wheel was rebuilt, its archive
was inspected for
`share/hawedit/requirements/host-gpu-windows-py311.txt`, and it replaced the
editable install in the same disposable environment. From the installed wheel:

```
python -I -m hawedit.environment --show-lock gpu
python -I -m hawedit.environment --extra media --extra gpu --lock <printed-lock>
python -I -m hawedit.gpu_runtime
python -m pip check
```

The lock resolved under `C:\hg-144447\share\hawedit\requirements`, the exact
inventory audit printed `hawedit-environment-ok`, the two-card smoke reproduced
the result above, and `pip check` reported no broken requirements.

## What this does not prove

- Driver 596.36 is observed, not distributed or hash-locked. The real compute
  smoke catches current driver/runtime incompatibility, but a future driver
  change remains an external deployment risk.
- Hash locking is not licence clearance. Direct framework licences have prior
  project evidence, but the 46-wheel transitive graph and CUDA/cuDNN notices
  still require a release legal/notices audit; KLPT is CC BY-SA 4.0.
- No Linux, WSL, Python 3.12, single-GPU, or non-3090-Ti GPU target is claimed.
- The manual self-hosted GitHub workflow is defined but was not run here.
- This qualifies the CUDA host, not the application visual path. The measured
  VideoChat3-4B limit on this card is eight frames at 21.57 GiB, while Stage 2
  plans up to 64 frames. Nine frames OOM. That model-memory/scene-window design
  gap remains an application acceptance blocker; an exact dependency graph
  cannot fix it.

Focused result: environment, GPU-runtime, host-lock, and release tests passed;
Ruff formatting/lint and mypy passed.
