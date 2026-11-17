# Existing Runtime Copy Preparation

Read-only preparation2026-10-13, not execution/admission. Launch handoff approval
is still pending. No namespace probes, SDK imports, installation or model work.
Baseline1fe64a60caa9d6a74357b4d50852c19dfbd75cf3/package5e9b8281 unchanged.

Raw C:/Users/Wareen/HawEditCopiedRuntimeInventory-1fe64a6-20261013 contains
exact observer/code/summary, critical binary hashes and static readelf outputs.
Source/HEAD/status unchanged. Observer65.829s, inventory65.6661280240005s,
Ubuntu kernel6.18.54.1, HawaPC01/Windows26300/Python3.12.10; trusted system
Python stdlib inventory only, never imported the inspected SDK. GNU readelf2.46.
StdoutSHA c4b05b1922c3f0f5564f477a6c8a85508c4f0afbba683ffa06d3eab3fbac42a8.

| Source Tree | Regular Files | Regular Bytes | Symlinks | Candidate Private Destination |
| --- | --- | --- | --- | --- |
| Existing uv CPython3.12.0 base | 2540 | 257711894 | 10 | /runtime_base |
| Existing selected generation site-packages | 36922 | 8098118449 | 0 | /sdk/site-packages |

Source roots: /home/ai/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu;
/mnt/c/Users/Wareen/AppData/Local/HawEdit/wsl-asr/venvs/Ubuntu-a218b3a5773a38323a6ecbf4/environment/lib/python3.12/site-packages.
Inventory refuses source symlink escapes/nonregular/multilink files and bounds
100000files/128GiB/270s. Symlinks are recorded, not copied as links. Exact
SnapshotFile declarations must materialize admitted aliases as independent
readonly regular copies. This summary does NOT hash every source file, freeze
whole directories, establish dynamic closure, or reserve RAM/VRAM.

## Loader Layout Requirements

Actual Python PT_INTERP is /lib64/ld-linux-x86-64.so.2; DT_NEEDED includes
$ORIGIN/../lib/libpython3.12.so.1.0 and pthread/dl/util/m/rt/c. Preserve executable
and base lib/stdlib layout under /runtime_base; include explicit copied loader
and resolved system-library aliases. Do not rely on host /home, /mnt, search
paths, ld.so.cache or installed venv symlinks being visible after root entry.

Actual torch _C needs libtorch_python. libtorch_python needs torch CPU/CUDA/c10/
shm, cudart12/cudnn9/cusparseLt/cufile, stdc++/gcc_s/c/pthread/dl and loader.
Its $ORIGIN-relative NVIDIA search paths require preserving torch/lib and nvidia
sibling structure under /sdk/site-packages, not copying only _C or a few DSOs.
Static tags are necessary, not proof of dynamic dlopen/JIT/data-file completeness.
No broad file broker or writable cache/scratch is authorized to cover omissions.

Critical binary identities captured: Python exe bf4365ac.../4206560bytes,
libpython2044b230.../216182000bytes, torch_C db1e4f96.../25481bytes,
libtorch_python3641ee8b.../27463257bytes, libtorch_cpu75540e9f.../430926857bytes,
libtorch_cuda e371cd8f.../1015364433bytes, plus c10/c10_cuda in raw JSON. Whole
SHA256 strings and stat-before/after checks retained; no model weights loaded.
Static Python dynamic/program logs SHA32cfe7e3929ded64def5840aed34c6cb167e3465bc66422e2ae46d4a40b5204c /
8644f349818ad09485510bc6e92a36ede19d0ca11a02ede041ac40bb131e682b;
torch-python dynamic SHA26e49f34a8db14911ad0087530193639fdd9b717453a97033e66e0532a2cf578.

## Implementation Inputs, Not A Grant

Complete candidate trees already exceed default4096files/1GiB. Existing rooted
Snapshot accepts explicit100000files/128GiB ceilings; do not lower coverage to
make a tiny fixture fit or silently raise policy. Select finite copy budgets
using actual declarations plus loader/system/driver/source/config/input closure.
Source package, models, champion, tokenizer, labelled input and resource checks
must still be genuinely bound before model release; current VEX/CI unresolved.
Fresh copied Python/Torch computation and complete ZAR38 output remain unproven.
