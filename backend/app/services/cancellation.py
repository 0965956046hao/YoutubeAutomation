"""Cooperative cancellation and cleanup of a worker's media subprocesses."""

import os
import signal
import subprocess
import threading
from typing import Callable


class CancelledError(Exception):
    pass


def stop_process(proc: subprocess.Popen) -> None:
    # A dedicated process group includes FFmpeg children spawned by yt-dlp.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class Cancellation:
    def __init__(self):
        self.event = threading.Event()
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()

    def check(self) -> None:
        if self.event.is_set():
            raise CancelledError("Đã hủy tác vụ.")

    def wait(self, seconds: float) -> None:
        self.event.wait(seconds)
        self.check()

    def cancel(self) -> None:
        with self._lock:
            self.event.set()
            for proc in self._processes:
                stop_process(proc)

    def attach(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self.check()
            self._processes.add(proc)

    def detach(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(proc)


class CancellableReader:
    """Check cancellation between the blocks httpx reads from a multipart file."""
    def __init__(self, source, cancel: Cancellation):
        self.source = source
        self.cancel = cancel

    def read(self, *args):
        self.cancel.check()
        return self.source.read(*args)

    def __getattr__(self, name):
        return getattr(self.source, name)


def run_process(
    command: list[str], timeout: float, *, cancel: Cancellation | None = None,
    on_line: Callable[[str], None] | None = None,
) -> str:
    cancel = cancel or Cancellation()
    cancel.check()
    try:
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Chưa cài {command[0]} (cài FFmpeg và yt-dlp).") from exc
    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        stop_process(proc)

    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    timer.start()
    output = ""
    try:
        cancel.attach(proc)
        assert proc.stdout is not None
        for line in proc.stdout:
            cancel.check()
            output += line
            if on_line:
                output = output[-1500:]
                on_line(line)
        proc.wait()
        cancel.check()
    finally:
        timer.cancel()
        timer.join()
        cancel.detach(proc)
        if proc.poll() is None:
            stop_process(proc)
        proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
    cancel.check()
    if timed_out.is_set():
        raise RuntimeError(f"{command[0]} vượt quá thời gian xử lý.")
    if proc.returncode:
        raise RuntimeError(f"{command[0]} thất bại: {output[-1500:]}")
    return output
