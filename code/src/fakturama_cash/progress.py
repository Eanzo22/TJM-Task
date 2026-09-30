"""Human-readable terminal status; never reports guessed percentages or business data."""
import sys
import threading
import time


class TerminalProgress:
    def __init__(self, *, enabled=True, stream=None, interval=10, clock=time.monotonic):
        if interval <= 0:
            raise ValueError("Progress interval must be positive")
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stderr
        self.interval = interval
        self.clock = clock
        self.started = clock()
        self.stage_started = self.started
        self.current = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if self.enabled:
            self._thread = threading.Thread(target=self._heartbeat, name="terminal-progress", daemon=True)
            self._thread.start()
        return self

    def _emit(self, message):
        elapsed = max(0, int(self.clock() - self.started))
        minutes, seconds = divmod(elapsed, 60)
        try:
            # stderr leaves stdout available for the existing machine-readable result.
            print(f"[{minutes:02d}:{seconds:02d}] {message}", file=self.stream, flush=True)
        except (OSError, ValueError):
            # A closed terminal/log pipe must not change the outcome of a UI action.
            self.enabled = False
            self._stop.set()

    def update(self, message):
        with self._lock:
            if not self.enabled or self._stop.is_set():
                return
            self.current = " ".join(str(message).splitlines())
            self.stage_started = self.clock()
            self._emit(self.current)

    def _heartbeat(self):
        # The main thread may be blocked in HTTP or UIA. This thread only prints;
        # it never retries requests, clicks controls, or changes workflow state.
        while not self._stop.wait(self.interval):
            with self._lock:
                if self.enabled and self.current and not self._stop.is_set():
                    duration = max(0, int(self.clock() - self.stage_started))
                    self._emit(f"Still working ({duration}s in this stage): {self.current}")

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def finish(self, message):
        self.update(message)
        # Stop before the CLI prints its final JSON, so no late heartbeat follows it.
        self.close()

    def __exit__(self, *_):
        self.close()
