"""Small Win32 ACL boundary for application-owned private checkpoint staging.

POSIX ``0700`` staging has no Windows equivalent in :mod:`pathlib`: newly created directories
inherit the parent DACL.  A custom model volume can therefore grant another principal write
access to a downloader's supposedly private tree.  These helpers create the directory with a
protected DACL atomically and then inspect every path through Win32 security APIs.  No localized
``icacls`` output is parsed in production.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Final

__all__ = ["WindowsSecurityError", "assert_private_windows_path", "create_private_directory"]


class WindowsSecurityError(RuntimeError):
    """A Windows filesystem object does not have HawEdit's private staging ACL."""


_ERROR_INSUFFICIENT_BUFFER: Final = 122
_SE_FILE_OBJECT: Final = 1
_OWNER_SECURITY_INFORMATION: Final = 0x00000001
_DACL_SECURITY_INFORMATION: Final = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION: Final = 0x80000000
_SE_DACL_PROTECTED: Final = 0x1000
_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER: Final = 1
_ACL_SIZE_INFORMATION_CLASS: Final = 2
_ACCESS_ALLOWED_ACE_TYPE: Final = 0
_FILE_ALL_ACCESS: Final = 0x001F01FF
_SYSTEM_SID: Final = "S-1-5-18"
_ADMINISTRATORS_SID: Final = "S-1-5-32-544"


class _SecurityAttributes(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _SidAndAttributes(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
    ]


class _TokenUser(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("User", _SidAndAttributes)
    ]


class _AclSizeInformation(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


class _AceHeader(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", wintypes.WORD),
    ]


class _AccessAllowedAce(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, object]]] = [  # type: ignore[assignment]
        ("Header", _AceHeader),
        ("Mask", wintypes.DWORD),
        ("SidStart", wintypes.DWORD),
    ]


@lru_cache(maxsize=1)
def _windows_libraries() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    if os.name != "nt":
        raise WindowsSecurityError("Windows private ACL operations require Windows")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.CreateDirectoryW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(_SecurityAttributes),
    ]
    kernel32.CreateDirectoryW.restype = wintypes.BOOL

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetSecurityDescriptorControl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi32.GetAclInformation.argtypes = [
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi32.GetAce.restype = wintypes.BOOL
    return advapi32, kernel32


def _win_error(operation: str, code: int | None = None) -> WindowsSecurityError:
    selected = ctypes.get_last_error() if code is None else code
    return WindowsSecurityError(f"{operation} failed with Win32 error {selected}")


def _sid_string(sid: wintypes.LPVOID) -> str:
    advapi32, kernel32 = _windows_libraries()
    converted = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(converted)):
        raise _win_error("ConvertSidToStringSidW")
    try:
        if converted.value is None:
            raise WindowsSecurityError("ConvertSidToStringSidW returned no SID")
        return converted.value
    finally:
        kernel32.LocalFree(converted)


def _current_user_sid() -> str:
    advapi32, kernel32 = _windows_libraries()
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise _win_error("OpenProcessToken")
    try:
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER or needed.value == 0:
            raise _win_error("GetTokenInformation(size)")
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, _TOKEN_USER, buffer, needed, ctypes.byref(needed)
        ):
            raise _win_error("GetTokenInformation")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        return _sid_string(token_user.User.Sid)
    finally:
        kernel32.CloseHandle(token)


def create_private_directory(path: Path) -> None:
    """Create ``path`` once with an atomically applied protected owner-only DACL."""
    advapi32, kernel32 = _windows_libraries()
    current_sid = _current_user_sid()
    sddl = (
        "D:P"
        f"(A;OICI;FA;;;{current_sid})"
        f"(A;OICI;FA;;;{_SYSTEM_SID})"
        f"(A;OICI;FA;;;{_ADMINISTRATORS_SID})"
    )
    descriptor = wintypes.LPVOID()
    descriptor_size = wintypes.DWORD()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), ctypes.byref(descriptor_size)
    ):
        raise _win_error("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        if not kernel32.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            raise _win_error(f"CreateDirectoryW({path})")
    finally:
        kernel32.LocalFree(descriptor)
    assert_private_windows_path(path, require_protected=True)


def assert_private_windows_path(path: Path, *, require_protected: bool) -> None:
    """Refuse owners or access-allowed ACEs outside user/SYSTEM/Administrators."""
    advapi32, kernel32 = _windows_libraries()
    owner = wintypes.LPVOID()
    dacl = wintypes.LPVOID()
    descriptor = wintypes.LPVOID()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0:
        raise _win_error(f"GetNamedSecurityInfoW({path})", int(result))
    try:
        current_sid = _current_user_sid()
        if _sid_string(owner) != current_sid:
            raise WindowsSecurityError(f"private staging path belongs to another principal: {path}")
        if not dacl:
            raise WindowsSecurityError(f"private staging path has a null DACL: {path}")

        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not advapi32.GetSecurityDescriptorControl(
            descriptor, ctypes.byref(control), ctypes.byref(revision)
        ):
            raise _win_error(f"GetSecurityDescriptorControl({path})")
        if require_protected and not (control.value & _SE_DACL_PROTECTED):
            raise WindowsSecurityError(
                f"private staging root inherits access from its parent: {path}"
            )

        information = _AclSizeInformation()
        if not advapi32.GetAclInformation(
            dacl,
            ctypes.byref(information),
            ctypes.sizeof(information),
            _ACL_SIZE_INFORMATION_CLASS,
        ):
            raise _win_error(f"GetAclInformation({path})")
        allowed = {current_sid, _SYSTEM_SID, _ADMINISTRATORS_SID}
        seen: set[str] = set()
        for index in range(information.AceCount):
            ace_pointer = wintypes.LPVOID()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                raise _win_error(f"GetAce({path}, {index})")
            ace = ctypes.cast(ace_pointer, ctypes.POINTER(_AccessAllowedAce)).contents
            if ace.Header.AceType != _ACCESS_ALLOWED_ACE_TYPE:
                raise WindowsSecurityError(f"private staging path has a non-allow ACE: {path}")
            if ace_pointer.value is None:
                raise WindowsSecurityError(f"private staging path has a null ACE: {path}")
            sid_pointer = wintypes.LPVOID(ace_pointer.value + _AccessAllowedAce.SidStart.offset)
            principal = _sid_string(sid_pointer)
            if principal not in allowed:
                raise WindowsSecurityError(
                    f"private staging path grants access to another principal: {path}"
                )
            if ace.Mask & _FILE_ALL_ACCESS != _FILE_ALL_ACCESS:
                raise WindowsSecurityError(
                    f"private staging path lacks full control for an allowed principal: {path}"
                )
            seen.add(principal)
        if seen != allowed:
            raise WindowsSecurityError(
                f"private staging path has an incomplete private DACL: {path}"
            )
    finally:
        kernel32.LocalFree(descriptor)
