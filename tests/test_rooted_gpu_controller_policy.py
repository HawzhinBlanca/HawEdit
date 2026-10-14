"""Actual combined kernel denials; not GPU worker/model admission."""

from __future__ import annotations

from pathlib import Path

from test_rooted_wsl_gpu import _ADMIT, _gpu_run


def test_rooted_gpu_owned_controller_fence_preserves_final_verification(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "snapshot._controller_fence()\n"
        "assert snapshot._controller_filters==snapshot._filters\n"
        "assert snapshot._controller_filters>0\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_gpu_controller_proves_landlock_and_seccomp_separately(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "snapshot._controller_fence()\n"
        "assert snapshot._entropy is not None\n"
        "try:fd=os.open('/dev/urandom',os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC)\n"
        "except OSError as exc:assert exc.errno==errno.EACCES,exc\n"
        "else:os.close(fd);raise AssertionError('Landlock writable entropy admitted')\n"
        "for path in ('/dev/urandom','/proc/self/fd/'+str(snapshot._entropy[0]),'/dev/dxg'):\n"
        " try:fd=os.open(path,os.O_RDWR|os.O_CLOEXEC)\n"
        " except OSError as exc:assert exc.errno==errno.EPERM,exc\n"
        " else:os.close(fd);raise AssertionError('Controller GPU/non-GPU write admitted')\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_gpu_unregistered_filter_cannot_change_default_policy_proof(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "from hawedit.linux_snapshot import _install_namespace_fence,_FenceRole\n"
        "_install_namespace_fence(native,entropy=True,gpu=False,role=_FenceRole.CONTROLLER)\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError as exc:\n"
        " assert 'uncertain' in str(exc) and snapshot._failed\n"
        "else:raise AssertionError('Unregistered filter profile admitted')",
    )


def test_rooted_gpu_controller_fence_cannot_be_installed_twice(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "snapshot._controller_fence()\n"
        "try:snapshot._controller_fence()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Controller fence replay admitted')\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_gpu_controller_filter_identity_cannot_be_supplied_as_boolean(
    tmp_path: Path,
) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "snapshot._controller_filters=True\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError as exc:assert snapshot._failed\n"
        "else:raise AssertionError('Caller True flag admitted as kernel evidence')",
    )
