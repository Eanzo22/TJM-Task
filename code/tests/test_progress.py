import io
import threading

import pytest

from fakturama_cash.progress import TerminalProgress


def test_elapsed_stage_messages_are_flushed():
    class Stream(io.StringIO):
        flush_count = 0
        def flush(self):
            self.flush_count += 1
            super().flush()
    stream = Stream()
    now = [100]
    with TerminalProgress(stream=stream, clock=lambda: now[0]) as progress:
        progress.update("Starting extraction")
        now[0] = 165
        progress.update("Checking totals")
    assert stream.getvalue().splitlines() == ["[00:00] Starting extraction", "[01:05] Checking totals"]
    assert stream.flush_count == 2
    assert not progress._thread.is_alive()


def test_heartbeat_while_main_thread_waits_and_cleanup_on_failure():
    tick = threading.Event()
    class Stream(io.StringIO):
        def write(self, text):
            result = super().write(text)
            if "Still working" in text:
                tick.set()
            return result
    stream = Stream()
    with pytest.raises(RuntimeError, match="simulated"):
        with TerminalProgress(stream=stream, interval=0.01) as progress:
            progress.update("Waiting for model response")
            assert tick.wait(timeout=3), "No heartbeat during blocked observation"
            raise RuntimeError("simulated request failure")
    output = stream.getvalue()
    assert "Still working" in output
    assert "Waiting for model response" in output
    assert "%" not in output
    assert "complete" not in output.lower()
    assert not progress._thread.is_alive()
    progress.update("This must not print after close")
    assert stream.getvalue() == output


def test_quiet_starts_no_worker_and_emits_nothing():
    stream = io.StringIO()
    with TerminalProgress(enabled=False, stream=stream) as progress:
        progress.update("Hidden")
        assert progress._thread is None
    assert stream.getvalue() == ""


def test_closed_progress_pipe_does_not_fail_business_action():
    stream = io.StringIO()
    stream.close()
    with TerminalProgress(stream=stream) as progress:
        progress.update("Action can continue")
        assert progress.enabled is False
    assert not progress._thread.is_alive()


def test_invalid_interval_rejected():
    with pytest.raises(ValueError, match="positive"):
        TerminalProgress(interval=0)


def test_finish_stops_worker_before_final_result_and_close_is_safe_twice():
    stream = io.StringIO()
    with TerminalProgress(stream=stream) as progress:
        progress.update("Checking data")
        progress.finish("Validation complete")
        assert not progress._thread.is_alive()
        progress.update("Should remain hidden")
        print('{"status":"validated"}', file=stream)
    assert stream.getvalue().splitlines()[-1] == '{"status":"validated"}'
    assert "Should remain hidden" not in stream.getvalue()
