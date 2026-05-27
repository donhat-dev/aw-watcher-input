import ctypes
import logging
import sys
from ctypes.util import find_library
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_REQUEST_TYPE_LISTEN_EVENT = 1
_ACCESS_GRANTED = 0


@dataclass(frozen=True)
class MacosInputPermissionState:
    listen_event: Optional[bool]
    accessibility: Optional[bool]
    satisfied: bool


class CtypesMacosPermissionBackend:
    def __init__(self):
        self.core_graphics = _load_framework("CoreGraphics")
        self.core_foundation = _load_framework("CoreFoundation")
        self.application_services = _load_framework("ApplicationServices")
        self.io_kit = _load_framework("IOKit")

    def has_listen_event_access(self) -> Optional[bool]:
        preflight = getattr(self.core_graphics, "CGPreflightListenEventAccess", None)
        if preflight is not None:
            preflight.restype = ctypes.c_bool
            return bool(preflight())
        return self._iohid_check_access()

    def request_listen_event_access(self) -> Optional[bool]:
        request = getattr(self.core_graphics, "CGRequestListenEventAccess", None)
        if request is not None:
            request.restype = ctypes.c_bool
            return bool(request())
        return self._iohid_request_access()

    def has_accessibility_trust(self) -> Optional[bool]:
        trusted = getattr(self.application_services, "AXIsProcessTrusted", None)
        if trusted is None:
            return None
        trusted.restype = ctypes.c_bool
        return bool(trusted())

    def request_accessibility_trust(self) -> Optional[bool]:
        request = getattr(self.application_services, "AXIsProcessTrustedWithOptions", None)
        if request is None:
            return None

        options = self._accessibility_prompt_options()
        if not options:
            return None

        request.argtypes = [ctypes.c_void_p]
        request.restype = ctypes.c_bool
        try:
            return bool(request(options))
        finally:
            self._cf_release(options)

    def _iohid_check_access(self) -> Optional[bool]:
        check = getattr(self.io_kit, "IOHIDCheckAccess", None)
        if check is None:
            return None
        check.argtypes = [ctypes.c_int]
        check.restype = ctypes.c_int
        return check(_REQUEST_TYPE_LISTEN_EVENT) == _ACCESS_GRANTED

    def _iohid_request_access(self) -> Optional[bool]:
        request = getattr(self.io_kit, "IOHIDRequestAccess", None)
        if request is None:
            return None
        request.argtypes = [ctypes.c_int]
        request.restype = ctypes.c_bool
        return bool(request(_REQUEST_TYPE_LISTEN_EVENT))

    def _accessibility_prompt_options(self) -> Optional[int]:
        try:
            prompt_key = ctypes.c_void_p.in_dll(
                self.application_services,
                "kAXTrustedCheckOptionPrompt",
            )
            cf_true = ctypes.c_void_p.in_dll(self.core_foundation, "kCFBooleanTrue")
        except ValueError:
            return None

        dictionary_create = self.core_foundation.CFDictionaryCreate
        dictionary_create.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        dictionary_create.restype = ctypes.c_void_p

        keys = (ctypes.c_void_p * 1)(prompt_key.value)
        values = (ctypes.c_void_p * 1)(cf_true.value)
        return dictionary_create(None, keys, values, 1, None, None)

    def _cf_release(self, ref: int) -> None:
        release = getattr(self.core_foundation, "CFRelease", None)
        if release is None:
            return
        release.argtypes = [ctypes.c_void_p]
        release.restype = None
        release(ref)


def ensure_macos_input_permissions(
    platform: str = sys.platform,
    backend=None,
    log: logging.Logger = logger,
) -> MacosInputPermissionState:
    if platform != "darwin":
        log.info("macOS input permission step skipped: platform=%s", platform)
        return MacosInputPermissionState(
            listen_event=True,
            accessibility=True,
            satisfied=True,
        )

    if backend is None:
        try:
            backend = CtypesMacosPermissionBackend()
        except Exception as exc:
            log.info("macOS input permission backend unavailable: %s", exc)
            return MacosInputPermissionState(
                listen_event=None,
                accessibility=None,
                satisfied=False,
            )

    log.info("macOS input permission preflight: checking ListenEvent and Accessibility")
    state = _read_state(backend, log)
    if state.satisfied:
        log.info(
            "macOS input permission already satisfied: listen_event=%s accessibility=%s",
            state.listen_event,
            state.accessibility,
        )
        return state

    log.info("macOS input permission missing; requesting Input Monitoring prompt")
    listen_result = _call_backend(
        "request_listen_event_access",
        backend.request_listen_event_access,
        log,
    )
    log.info("macOS Input Monitoring request returned: %s", listen_result)

    state = _read_state(backend, log)
    if state.satisfied:
        log.info(
            "macOS input permission satisfied after Input Monitoring request: listen_event=%s accessibility=%s",
            state.listen_event,
            state.accessibility,
        )
        return state

    log.info("macOS input permission still missing; requesting Accessibility prompt")
    accessibility_result = _call_backend(
        "request_accessibility_trust",
        backend.request_accessibility_trust,
        log,
    )
    log.info("macOS Accessibility request returned: %s", accessibility_result)

    state = _read_state(backend, log)
    if state.satisfied:
        log.info(
            "macOS input permission satisfied after Accessibility request: listen_event=%s accessibility=%s",
            state.listen_event,
            state.accessibility,
        )
    else:
        log.info(
            "macOS input permission still missing after prompt requests: listen_event=%s accessibility=%s",
            state.listen_event,
            state.accessibility,
        )
    return state


def _read_state(backend, log: logging.Logger) -> MacosInputPermissionState:
    listen_event = _call_backend(
        "has_listen_event_access",
        backend.has_listen_event_access,
        log,
    )
    accessibility = _call_backend(
        "has_accessibility_trust",
        backend.has_accessibility_trust,
        log,
    )
    satisfied = listen_event is True or accessibility is True
    log.info(
        "macOS input permission state: listen_event=%s accessibility=%s satisfied=%s",
        listen_event,
        accessibility,
        satisfied,
    )
    return MacosInputPermissionState(
        listen_event=listen_event,
        accessibility=accessibility,
        satisfied=satisfied,
    )


def _call_backend(name: str, func, log: logging.Logger):
    try:
        return func()
    except Exception as exc:
        log.info("macOS input permission step failed: %s: %s", name, exc)
        return None


def _load_framework(name: str):
    path = find_library(name) or f"/System/Library/Frameworks/{name}.framework/{name}"
    return ctypes.cdll.LoadLibrary(path)
