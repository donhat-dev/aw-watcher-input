import logging
import threading
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


class EventFactory(metaclass=ABCMeta):
    def __init__(self) -> None:
        self.new_event = threading.Event()
        self._reset_data()

    @abstractmethod
    def _reset_data(self) -> None:
        self.event_data: Dict[str, Any] = {}

    def next_event(self) -> dict:
        self.new_event.clear()
        data = self.event_data
        self._reset_data()
        return data

    def has_new_event(self) -> bool:
        return self.new_event.is_set()


class KeyboardListener(EventFactory):
    def __init__(self):
        EventFactory.__init__(self)
        self.logger = logger.getChild("keyboard")
        self._listener = None

    def start(self):
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=self.on_press, on_release=self.on_release
        )
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()

    def is_alive(self) -> bool:
        return self._listener is not None and self._listener.is_alive()

    def _reset_data(self):
        self.event_data = {"presses": 0}

    def on_press(self, key):
        self.event_data["presses"] += 1
        self.new_event.set()

    def on_release(self, key):
        pass


class MouseListener(EventFactory):
    def __init__(self):
        EventFactory.__init__(self)
        self.logger = logger.getChild("mouse")
        self.pos = None
        self._listener = None

    def _reset_data(self):
        self.event_data = defaultdict(int)
        self.event_data.update(
            {"clicks": 0, "deltaX": 0, "deltaY": 0, "scrollX": 0, "scrollY": 0}
        )

    def start(self):
        from pynput import mouse

        self._listener = mouse.Listener(
            on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll
        )
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()

    def is_alive(self) -> bool:
        return self._listener is not None and self._listener.is_alive()

    def on_move(self, x, y):
        newpos = (x, y)
        if not self.pos:
            self.pos = newpos

        delta = tuple(self.pos[i] - newpos[i] for i in range(2))
        self.event_data["deltaX"] += abs(delta[0])
        self.event_data["deltaY"] += abs(delta[1])

        self.pos = newpos
        self.new_event.set()

    def on_click(self, x, y, button, down):
        if down:
            self.event_data["clicks"] += 1
            self.new_event.set()

    def on_scroll(self, x, y, scrollx, scrolly):
        self.event_data["scrollX"] += abs(scrollx)
        self.event_data["scrollY"] += abs(scrolly)
        self.new_event.set()
