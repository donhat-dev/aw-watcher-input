import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any, Dict, List, Optional

import aw_client
import click
from aw_core import Event

from .listeners import KeyboardListener, MouseListener
from .macos_permissions import ensure_macos_input_permissions

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def _macos_input_permission_hint() -> str:
    return (
        "On macOS, input capture requires Accessibility/Input Monitoring permission "
        "for ActivityWatch or the bundled aw-watcher-input helper."
    )


def _log_file_path() -> Path:
    from aw_core.dirs import get_log_dir
    env_log_dir = os.getenv("AW_LOG_DIR")
    if env_log_dir:
        log_dir = Path(env_log_dir).expanduser()
    elif os.getenv("AW_LOG_ROOT"):
        log_dir = Path(os.environ["AW_LOG_ROOT"]).expanduser() / "aw-watcher-input"
    else:
        log_dir = Path(get_log_dir("aw-watcher-input"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "aw-watcher-input.log"


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(), logging.FileHandler(_log_file_path(), encoding="utf-8")]
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _load_toml_config(config_path: Optional[str]) -> Dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else _find_default_config()
    if not path or not path.exists():
        return {}
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def _find_default_config() -> Optional[Path]:
    from aw_core.dirs import get_config_dir
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "config.toml")
    candidates.append(Path(get_config_dir("aw-watcher-input")) / "config.toml")
    candidates.append(Path.cwd() / "config.toml")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@click.command()
@click.option("--testing", is_flag=True)
@click.option("--debug", is_flag=True, help="Enable verbose logging and write detailed logs to aw-watcher-input.log")
@click.option("--config", default=None, help="Path to config.toml")
def main(testing: bool, debug: bool, config: Optional[str]):
    _configure_logging(debug)
    raw_config = _load_toml_config(config)
    watcher_config = raw_config.get("watcher", {})
    logger.info("Starting watcher-input")
    logger.debug("Python executable: %s", sys.executable)
    logger.debug("Frozen executable: %s", getattr(sys, "frozen", False))
    logger.debug("Current working directory: %s", os.getcwd())
    logger.debug("Log file: %s", _log_file_path())
    if sys.platform == "darwin":
        logger.info(_macos_input_permission_hint())
        permission_state = ensure_macos_input_permissions(log=logger)
        if not permission_state.satisfied:
            logger.warning(
                "macOS input permission is still missing; exiting watcher-input without error. "
                "Grant Input Monitoring/Accessibility permission, then quit and restart ActivityWatch."
            )
            return

    client = aw_client.ActivityWatchClient("aw-watcher-input", testing=testing)
    logger.debug("Created ActivityWatchClient host=%s port=%s testing=%s", getattr(client, "host", None), getattr(client, "port", None), testing)
    logger.info("Waiting for aw-server to start")
    client.wait_for_start()
    logger.info("Connecting to aw-server")
    client.connect()

    # Create bucket
    bucket_name = "{}_{}".format(client.client_name, client.client_hostname)
    eventtype = "os.hid.input"
    logger.info("Creating bucket %s of type %s", bucket_name, eventtype)
    client.create_bucket(bucket_name, eventtype, queued=False)
    poll_time = watcher_config.get("poll_time", 5)

    logger.info("Starting keyboard listener")
    keyboard = KeyboardListener()
    try:
        keyboard.start()
    except Exception as exc:
        if sys.platform == "darwin":
            logger.exception("Failed to start keyboard listener. %s", _macos_input_permission_hint())
        raise RuntimeError("Failed to start keyboard listener") from exc
    logger.info("Starting mouse listener")
    mouse = MouseListener()
    try:
        mouse.start()
    except Exception as exc:
        if sys.platform == "darwin":
            logger.exception("Failed to start mouse listener. %s", _macos_input_permission_hint())
        raise RuntimeError("Failed to start mouse listener") from exc

    now = datetime.now(tz=timezone.utc)
    logger.info("Watcher loop started with poll_time=%s", poll_time)

    while True:
        last_run = now

        # we want to ensure that the polling happens with a predictable cadence
        time_to_sleep = poll_time - datetime.now().timestamp() % poll_time
        # ensure that the sleep time is between 0 and poll_time (if system time is changed, this might be negative)
        time_to_sleep = max(min(time_to_sleep, poll_time), 0)
        sleep(time_to_sleep)

        now = datetime.now(tz=timezone.utc)

        # If input:    Send a heartbeat with data, ensure the span is correctly set, and don't use pulsetime.
        # If no input: Send a heartbeat with all-zeroes in the data, use a pulsetime.
        # FIXME: Doesn't account for scrolling
        # FIXME: Counts both keyup and keydown
        keyboard_data = keyboard.next_event()
        mouse_data = mouse.next_event()
        logger.debug("keyboard_data=%s mouse_data=%s", keyboard_data, mouse_data)
        merged_data = dict(**keyboard_data, **mouse_data)
        e = Event(timestamp=last_run, duration=(now - last_run), data=merged_data)

        pulsetime = 0.0
        if all(map(lambda v: v == 0, merged_data.values())):
            pulsetime = poll_time + 0.1
            logger.info("No new input")
        else:
            logger.info(f"New input: {e}")

        logger.debug("Sending heartbeat to bucket=%s pulsetime=%s data=%s", bucket_name, pulsetime, merged_data)
        client.heartbeat(bucket_name, e, pulsetime=pulsetime, queued=True)
