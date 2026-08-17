# Editable model-fetch environment acceptance

Date: 2026-08-15
Host: HawEdit Windows workstation
Interpreter: CPython 3.12, `D:\HawEdit-model-fetch-env\Scripts\python.exe`
Source checkout: `D:\HawEdit-independent\active-speaker`

## Purpose

Prove the documented source-checkout model-fetch environment works as a real PEP 660 editable
install while preserving the same code-bound dependency-lock enforcement used by the wheel.

## Procedure and result

1. Ran the documented locked installer against the dedicated environment:

   `scripts/install-host.sh D:/HawEdit-model-fetch-env/Scripts/python.exe models`

2. The installer authenticated and found all 19 exact Windows/CPython 3.12 model-fetch
   distributions, passed `pip check`, replaced the diagnostic wheel with a PEP 660 editable
   HawEdit install rooted at this checkout, and completed its exact source environment audit.
3. Under isolated import mode, called the same production preflight used by
   `hawedit.model_fetch`:

   `audit_installed_profile("models")` followed by `_download_client()`.

4. Observed:

   `EDITABLE_PROFILE_OK D:\HawEdit-independent\active-speaker\requirements\host-models-windows-py312.txt 19 huggingface_hub._snapshot_download.snapshot_download`

This proves the editable branch authenticated the current checkout lock and complete locked
inventory, then resolved the genuine lazy export from `huggingface-hub==0.36.2`. It made no
model-network request. Wheel lock resolution remains separately covered by the existing
RECORD/tamper and release smoke tests.

## Scope

This is host dependency/preflight evidence, not a claim that every model runtime is ready.
Checkpoint bytes and runtime loaders are reported independently by §7 readiness.
