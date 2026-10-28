#!/usr/bin/env python3

import collections
import collections.abc
import enum
import os
import re
import select
import socket
import time

import evdev

KEYBOARD_REGEX = r"^ITE Tech\. Inc\. ITE Device\([0-9]+\) Keyboard$"
THRESHOLD_NS = 8_000_000


class Action(enum.Enum):
    FORWARD = 1
    DROP = 2
    WAIT = 3


def event_time_ns(event: evdev.InputEvent):
    return event.sec * 1_000_000_000 + event.usec * 1_000


class Debouncer:
    def __init__(self):
        self.last_event_ns = -THRESHOLD_NS
        self.last_space_down_ns = -THRESHOLD_NS
        self.armed = 0
        self.suppress = False
        self.pending: collections.deque[tuple[evdev.InputEvent, int]] = collections.deque()

    def add(self, events: collections.abc.Iterable[evdev.InputEvent], now_ns: int):
        self.pending.extend(
            (event, now_ns + THRESHOLD_NS)
            for event in events if event.type == evdev.ecodes.EV_KEY
        )

    def timeout_s(self, now_ns: int):
        if not self.pending:
            return None
        _, deadline_ns = self.pending[0]
        return max(0, deadline_ns - now_ns) / 1_000_000_000

    def flush(self, now_ns: int):
        while self.pending:
            event, deadline_ns = self.pending[0]
            action = self.process_event(event, deadline_ns, now_ns)

            if action == Action.WAIT:
                break

            self.pending.popleft()

            if action == Action.FORWARD:
                yield event

    def process_event(self, event: evdev.InputEvent, deadline_ns: int, now_ns: int):
        timestamp_ns = event_time_ns(event)

        if event.code != evdev.ecodes.KEY_SPACE:
            self.last_event_ns = timestamp_ns
            if self.armed:
                self.armed -= 1
            return Action.FORWARD

        if event.value == 1:  # KEYDOWN
            return self.process_space_down(timestamp_ns, deadline_ns, now_ns)

        if self.suppress:
            if event.value == 0:  # KEYUP
                self.suppress = False
            return Action.DROP

        if event.value == 0 and timestamp_ns - self.last_space_down_ns < THRESHOLD_NS:
            self.armed = 2

        return Action.FORWARD

    def process_space_down(self, timestamp_ns: int, deadline_ns: int, now_ns: int):
        if not self.armed:
            self.suppress = False
            self.last_space_down_ns = timestamp_ns
            return Action.FORWARD

        nearby = (
            0 <= timestamp_ns - self.last_event_ns <= THRESHOLD_NS
            or any(
                other.code != evdev.ecodes.KEY_SPACE
                and 0 <= event_time_ns(other) - timestamp_ns <= THRESHOLD_NS
                for other, _ in self.pending
            )
        )
        if nearby:
            self.armed = 0
            self.suppress = True
            return Action.DROP

        if now_ns < deadline_ns:
            return Action.WAIT

        self.armed = 0
        self.suppress = False
        self.last_space_down_ns = timestamp_ns
        return Action.FORWARD


def sd_notify(message: str):
    path = os.getenv("NOTIFY_SOCKET")
    if not path:
        return

    if path.startswith("@"):
        path = "\0" + path[1:]

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.connect(path)
        sock.sendall(message.encode())
    finally:
        sock.close()


def get_keyboard():
    pattern = re.compile(KEYBOARD_REGEX)

    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        if pattern.search(dev.name):
            return dev

    raise RuntimeError(f"Keyboard not found: {KEYBOARD_REGEX}")


def main(path: str | os.PathLike[str]):
    dev = evdev.InputDevice(path)
    dev.grab()
    ui = evdev.UInput.from_device(dev, name="Legion Spacebar Debounced Keyboard")

    sd_notify("READY=1")

    debouncer = Debouncer()

    try:
        while True:
            timeout_s = debouncer.timeout_s(time.monotonic_ns())
            readable, _, _ = select.select([dev], [], [], timeout_s)
            if readable:
                debouncer.add(dev.read(), time.monotonic_ns())

            for event in debouncer.flush(time.monotonic_ns()):
                ui.write_event(event)
                ui.syn()

    finally:
        try:
            dev.ungrab()
        finally:
            ui.close()


if __name__ == "__main__":
    main(get_keyboard())
