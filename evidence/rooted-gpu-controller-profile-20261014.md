---
commit: 8265beee1257f3ad21d66ceac934ea6ca7d92c37
media_sha256: n/a (copied ELF/Python and genuine kernel policy tests; no media inference)
host: HawaPC01 Threadripper3990X Windows26300 CPython3.12.10; WSL6.18.54.1-microsoft-standard-WSL2 bootstrapPython3.14.4 copiedPython3.12.0
command: .venv/Scripts/python.exe -m pytest tests/test_rooted_gpu_controller_policy.py tests/test_rooted_wsl_gpu.py tests/test_rooted_controller.py tests/test_rooted_worker.py tests/test_linux_snapshot.py tests/test_rooted_linux_image.py tests/test_rooted_kernel_entropy.py tests/test_linux_thread_registry.py tests/test_linux_thread_name.py tests/test_linux_scope.py tests/test_linux_prepared_view.py tests/test_linux_joined_view.py tests/test_claims.py --junitxml=C:/Users/Wareen/HawEditGPUControllerPolicy-final-cohort-20261014.xml
status: WIP first PA1 profile unit; canonical full gate/CI and production GPU/ASR admission not claimed
libraries: pytest9.1.1 ruff0.9.6 mypy1.15.0; no Torch/model import
---

# Owned Controller Filter Profile

Approved protected-ASR plan, D-329. Actual pre-edit13pair and introduced3pair
Serena maps with hashes are in the impact map. No diagnostic ceiling, ordinary
GPU proof, model policy, gate step or independent security review changed.

Final affected cohort390passed/0failures/errors/skips,149.06s. XML SHA256
54c1230a510d2c84e9cd8997656a51f1b754e3395c8c8d2520cbe57e368fb552.
The full original joined-view module is included in this affected run. Strict
fast checks408files and changed4file formatting pass, not a canonical gate pass.
Initial new policy run4failed/1passed and original-controller binding run
3failed/17passed are retained externally; no suppression or fixture adjustment.
First43policy/GPU cases pass21.52s; intermediate323affected cases pass133.31s,
but annotation/formatting changed during that run, so use the final cohort instead.

The exact existing kernel-installed controller fence is recorded internally,
then the existing final Snapshot filter is stacked and verified before output.
GPU profile proves exact EACCES on the broker-shaped direct entropy open and
exact EPERM on O_RDWR direct/alias opens. Default GPU profile retains EACCES.
Unregistered filter, replay and boolean evidence refuse. GPU worker launch is
still refused: live broker servicing before final controller Landlock and actual
copied CUDA/resource/producer/ASR transport remain separate required work.

Source SHA256:
- linux_snapshot.py: 4a1c42c708f555c262e570897ef75f38bbfd3e0ae7a112be053008405bdb6d30
- linux_rooted_launch.py: 7f32964cc66be8be17fcd7d3a0189706d784a82459862a2be16c8d49d5d6d171
- test_rooted_controller.py: 771292bc5e988a19b83d74ff92c364bc1d29c5da27e088eea3b4c5f62ba167f2
- test_rooted_gpu_controller_policy.py: 67fd530664f69648f3289e5c0c7564113c3a1b9589bed6dec8c056c7544a197f

No fresh ZAR transcript, accurate-caption/meaning claim, new reel, publication,
native-editor approval, security waiver, CI success or10/10 verdict follows.
