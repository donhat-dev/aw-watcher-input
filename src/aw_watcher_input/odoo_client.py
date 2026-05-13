from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import socket
import ssl
import time
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class OdooPushConfig:
    enabled: bool = False
    base_url: str = "http://localhost:8069"
    pin_code: str = ""
    token: str = ""
    api_secret: str = ""
    sign_requests: bool = True
    employee_id: Optional[int] = None
    device_id: str = ""
    device_name: str = ""
    timeout_secs: float = 10.0
    push_metadata_events: bool = True
    push_screenshots: bool = False


class OdooActivityTrackingClient:
    def __init__(self, config: OdooPushConfig, agent_version: str = "0.1.0") -> None:
        self.config = config
        self.agent_version = agent_version
        self.base_url = (config.base_url or "http://localhost:8069").rstrip("/")
        self.hostname = socket.gethostname()
        self.device_id = config.device_id or self.hostname
        self._warned_disabled = False
        self._parsed_url = urlparse(self.base_url)
        self._conn: Optional[http.client.HTTPConnection] = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and (self.config.token or self.config.pin_code or self.config.employee_id))

    def start(self) -> None:
        if not self.enabled:
            if self.config.enabled and not (self.config.token or self.config.pin_code or self.config.employee_id) and not self._warned_disabled:
                logger.warning("Odoo push is enabled without token, pin_code, or employee_id; skipping Odoo sync")
                self._warned_disabled = True
        return

    def stop(self) -> None:
        self._close_conn()

    def _get_conn(self) -> http.client.HTTPConnection:
        if self._conn is None:
            host = self._parsed_url.hostname or "localhost"
            port = self._parsed_url.port
            timeout = self.config.timeout_secs
            if self._parsed_url.scheme == "https":
                self._conn = http.client.HTTPSConnection(
                    host, port, timeout=timeout, context=ssl.create_default_context()
                )
            else:
                self._conn = http.client.HTTPConnection(host, port, timeout=timeout)
        return self._conn

    def _close_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def push_bucket_events(self, bucket_id: str, bucket_type: str, events: Iterable[Dict[str, Any]]) -> None:
        if not self.enabled or not self.config.push_metadata_events:
            return
        event_list = self._filter_duration_events(events)
        if not event_list:
            return
        self.start()
        self._post(
            "/api/v1/activity_tracking/bucket-events",
            {
                "device": self._device_payload(),
                "bucket": self._bucket_payload(bucket_id, bucket_type),
                "last_event_at": event_list[-1].get("timestamp") or _now_iso(),
                "events": event_list,
            },
        )

    def _device_payload(self) -> Dict[str, Any]:
        return {
            "id": self.device_id,
            "name": self.config.device_name or self.device_id,
            "hostname": self.hostname,
            "platform": _platform_name(),
            "agent_version": self.agent_version,
        }

    def _bucket_payload(self, bucket_id: str, bucket_type: str) -> Dict[str, Any]:
        return {
            "id": bucket_id,
            "name": bucket_id,
            "type": bucket_type,
            "client_name": self.agent_version.split("/", 1)[0],
            "hostname": self.hostname,
        }

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        body = dict(payload)
        if self.config.pin_code:
            body["pin_code"] = self.config.pin_code
        if self.config.token:
            body["token"] = self.config.token
        if self.config.employee_id:
            body["employee_id"] = self.config.employee_id
        if self.config.sign_requests and self.config.api_secret:
            timestamp = str(time.time())
            nonce = str(uuid4())
            payload_str = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
            signature_payload = f"{timestamp}|{nonce}|{payload_str}"
            signature = hmac.new(
                self.config.api_secret.encode("utf-8"),
                signature_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            body.update({"_timestamp": timestamp, "_nonce": nonce, "_signature": signature})
        body_bytes = json.dumps(body, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body_bytes)),
        }
        for attempt in range(2):
            try:
                conn = self._get_conn()
                conn.request("POST", path, body_bytes, headers)
                resp = conn.getresponse()
                data = resp.read().decode("utf-8")
                if resp.status >= 400:
                    logger.warning("Odoo push failed: HTTP %s %s", resp.status, data[:200])
                    return None
                return json.loads(data) if data else None
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError, OSError) as exc:
                logger.debug("Odoo connection lost (%s), reconnecting", exc)
                self._close_conn()
                if attempt == 0:
                    continue
                return None
            except Exception as exc:
                logger.warning("Odoo push failed: %s", exc)
                self._close_conn()
                return None
        return None

    def _filter_duration_events(self, events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered_events = []
        for event in events:
            duration = event.get("duration") or 0
            try:
                duration_value = float(duration)
            except (TypeError, ValueError):
                logger.debug("Skipping event with invalid duration: %s", event)
                continue
            if duration_value <= 0:
                continue
            normalized = dict(event)
            normalized["duration"] = duration_value
            filtered_events.append(normalized)
        return filtered_events


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _platform_name() -> str:
    import platform

    return platform.platform()
