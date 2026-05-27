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
    screen_recording: Optional[bool]
    satisfied: bool


class CtypesMacosPermissionBackend:
    def __init__(self):
        self.core_graphics = _load_framework("CoreGraphics")
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

    def has_screen_recording_access(self) -> Optional[bool]:
        preflight = getattr(self.core_graphics, "CGPreflightScreenCaptureAccess", None)
        if preflight is None:
            return None
        preflight.restype = ctypes.c_bool
        return bool(preflight())

    def request_screen_recording_access(self) -> Optional[bool]:
        request = getattr(self.core_graphics, "CGRequestScreenCaptureAccess", None)
        if request is None:
            return None
        request.restype = ctypes.c_bool
        return bool(request())

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


def ensure_macos_input_permissions(
    platform: str = sys.platform,
    backend=None,
    log: logging.Logger = logger,
) -> MacosInputPermissionState:
    if platform != "darwin":
        log.info("macOS input permission step skipped: platform=%s", platform)
        return MacosInputPermissionState(
            listen_event=True,
            screen_recording=True,
            satisfied=True,
        )

    if backend is None:
        try:
            backend = CtypesMacosPermissionBackend()
        except Exception as exc:
            log.info("macOS input permission backend unavailable: %s", exc)
            return MacosInputPermissionState(
                listen_event=None,
                screen_recording=None,
                satisfied=False,
            )

    log.info("macOS input permission preflight: checking Input Monitoring and Screen Recording")
    state = _read_state(backend, log)
    if state.satisfied:
        log.info(
            "macOS input permission already satisfied: listen_event=%s screen_recording=%s",
            state.listen_event,
            state.screen_recording,
        )
        return state

    if state.listen_event is not True:
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
            "macOS input permission satisfied after Input Monitoring request: listen_event=%s screen_recording=%s",
            state.listen_event,
            state.screen_recording,
        )
        return state

    if state.screen_recording is not True:
        log.info("macOS screen recording permission missing; requesting Screen Recording prompt")
        screen_result = _call_backend(
            "request_screen_recording_access",
            backend.request_screen_recording_access,
            log,
        )
        log.info("macOS Screen Recording request returned: %s", screen_result)

    state = _read_state(backend, log)
    if state.satisfied:
        log.info(
            "macOS input permission satisfied after Screen Recording request: listen_event=%s screen_recording=%s",
            state.listen_event,
            state.screen_recording,
        )
    else:
        log.info(
            "macOS input permission still missing after prompt requests: listen_event=%s screen_recording=%s",
            state.listen_event,
            state.screen_recording,
        )
    return state


def _read_state(backend, log: logging.Logger) -> MacosInputPermissionState:
    listen_event = _call_backend(
        "has_listen_event_access",
        backend.has_listen_event_access,
        log,
    )
    screen_recording = _call_backend(
        "has_screen_recording_access",
        backend.has_screen_recording_access,
        log,
    )
    satisfied = listen_event is True and screen_recording is True
    log.info(
        "macOS input permission state: listen_event=%s screen_recording=%s satisfied=%s",
        listen_event,
        screen_recording,
        satisfied,
    )
    return MacosInputPermissionState(
        listen_event=listen_event,
        screen_recording=screen_recording,
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
