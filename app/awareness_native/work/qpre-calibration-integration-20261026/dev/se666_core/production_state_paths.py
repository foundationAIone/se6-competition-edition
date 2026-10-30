"""Trusted current-user roots for production-local SE6 state.

Ambient environment variables are process input, not operating-system
authority.  Production callers therefore resolve Windows Local AppData through
the Known Folder API.  Explicit ``environ``/``platform_name``/``home`` values
remain available only to pure path-calculation tests and must never be passed
by production constructors.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Mapping
from ctypes import wintypes
from pathlib import Path
from uuid import UUID


class ProductionStatePathError(RuntimeError):
    """The operating system could not establish a trusted local-state root."""


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    )


def _guid(value: str) -> _GUID:
    parsed = UUID(value)
    data4 = (ctypes.c_ubyte * 8)(*parsed.bytes[8:])
    return _GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version, data4)


_FOLDERID_LOCAL_APP_DATA = _guid("F1B32785-6FBA-4FCF-9D55-7B8E7F157091")


def _windows_current_user_local_appdata() -> Path:
    """Resolve FOLDERID_LocalAppData without consulting ``LOCALAPPDATA``."""

    if os.name != "nt":
        raise ProductionStatePathError("WINDOWS_KNOWN_FOLDER_UNAVAILABLE")
    output = ctypes.c_wchar_p()
    ole32 = None
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        function = shell32.SHGetKnownFolderPath
        function.argtypes = (
            ctypes.POINTER(_GUID),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        )
        function.restype = ctypes.c_long
        result = function(
            ctypes.byref(_FOLDERID_LOCAL_APP_DATA),
            0,
            None,
            ctypes.byref(output),
        )
        if result != 0 or not output.value:
            raise ProductionStatePathError(
                f"WINDOWS_LOCAL_APPDATA_RESOLUTION_FAILED:{result & 0xFFFFFFFF:08x}"
            )
        return Path(output.value).resolve(strict=False)
    except ProductionStatePathError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ProductionStatePathError("WINDOWS_LOCAL_APPDATA_RESOLUTION_FAILED") from exc
    finally:
        if output.value and ole32 is not None:
            try:
                ole32.CoTaskMemFree(ctypes.cast(output, ctypes.c_void_p))
            except (AttributeError, OSError):
                pass


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = (
        ("Sid", ctypes.c_void_p),
        ("Attributes", wintypes.DWORD),
    )


class _TOKEN_USER(ctypes.Structure):
    _fields_ = (("User", _SID_AND_ATTRIBUTES),)


def _windows_current_user_sid() -> str:
    """Read the current process token SID without environment/user-name input."""

    if os.name != "nt":
        raise ProductionStatePathError("WINDOWS_TOKEN_UNAVAILABLE")
    token = wintypes.HANDLE()
    sid_text = ctypes.c_wchar_p()
    try:
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        kernel32.GetCurrentProcess.argtypes = ()
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        )
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        )
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            raise ProductionStatePathError("WINDOWS_TOKEN_UNAVAILABLE")
        required = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        if required.value == 0:
            raise ProductionStatePathError("WINDOWS_TOKEN_USER_UNAVAILABLE")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            1,
            buffer,
            required,
            ctypes.byref(required),
        ):
            raise ProductionStatePathError("WINDOWS_TOKEN_USER_UNAVAILABLE")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
        if not advapi32.ConvertSidToStringSidW(
            token_user.User.Sid, ctypes.byref(sid_text)
        ):
            raise ProductionStatePathError("WINDOWS_SID_CONVERSION_FAILED")
        if not sid_text.value:
            raise ProductionStatePathError("WINDOWS_SID_CONVERSION_FAILED")
        return sid_text.value
    except ProductionStatePathError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ProductionStatePathError("WINDOWS_TOKEN_UNAVAILABLE") from exc
    finally:
        if sid_text.value:
            try:
                ctypes.windll.kernel32.LocalFree(
                    ctypes.cast(sid_text, ctypes.c_void_p)
                )
            except (AttributeError, OSError):
                pass
        if token:
            try:
                ctypes.windll.kernel32.CloseHandle(token)
            except (AttributeError, OSError):
                pass


def trusted_current_user_identifier() -> str:
    """Return an OS-authoritative, stable identifier for the current account."""

    if os.name == "nt":
        return _windows_current_user_sid()
    try:
        return f"uid:{os.getuid()}"
    except (AttributeError, OSError) as exc:
        raise ProductionStatePathError("CURRENT_USER_IDENTIFIER_UNAVAILABLE") from exc


def trusted_local_state_root(
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return a production-trusted root or an explicitly injected test root.

    With no arguments, mutable environment roots are ignored.  Supplying any
    argument selects deterministic test-calculation behavior; production
    constructors independently reject those arguments.
    """

    explicit_test_inputs = any(
        value is not None for value in (environ, platform_name, home)
    )
    if not explicit_test_inputs:
        if os.name == "nt":
            return _windows_current_user_local_appdata()
        return (Path.home() / ".local" / "state").resolve(strict=False)

    values = {} if environ is None else environ
    platform = os.name if platform_name is None else platform_name
    user_home = Path.home() if home is None else Path(home)
    if platform == "nt":
        raw = values.get("LOCALAPPDATA", "").strip()
        root = Path(raw) if raw else user_home / "AppData" / "Local"
    else:
        raw = values.get("XDG_STATE_HOME", "").strip()
        root = Path(raw) if raw else user_home / ".local" / "state"
    return root.expanduser().resolve(strict=False)


__all__ = [
    "ProductionStatePathError",
    "trusted_current_user_identifier",
    "trusted_local_state_root",
]
