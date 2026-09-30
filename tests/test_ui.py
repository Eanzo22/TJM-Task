import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.ui import UIAAdapter, resolve, wait_stable
from fakturama_cash.workflow import ACTIONS, QUERIES


class Clock:
    def __init__(self):
        self.now = 0
    def time(self):
        return self.now
    def sleep(self, value):
        self.now += value


def test_wait_until_results_stable():
    clock = Clock()
    results = iter([[], [{"sku": "A"}], [{"sku": "A"}], [{"sku": "A"}], [{"sku": "A"}]])
    assert wait_stable(lambda: next(results), timeout=1, interval=0.1, stable_for=0.2,
                       clock=clock.time, sleep=clock.sleep) == [{"sku": "A"}]


def test_unstable_results_timeout():
    clock = Clock()
    with pytest.raises(ReviewRequired, match="stable state"):
        wait_stable(lambda: clock.now, timeout=0.5, interval=0.1,
                    clock=clock.time, sleep=clock.sleep)


def test_incomplete_profile_cannot_start():
    adapter = UIAAdapter({"calibrated": False}, desktop=object())
    with pytest.raises(ReviewRequired, match="not fully calibrated"):
        adapter.preflight(ACTIONS, QUERIES)


def test_template_is_lookup_not_eval():
    assert resolve("${input.items.0.sku}", {"input": {"items": [{"sku": "A"}]}}) == "A"
    assert resolve("__import__('os').system('bad')", {}) == "__import__('os').system('bad')"


def test_complete_profile_check_does_not_connect():
    profile = {"calibrated": True, "actions": {"example": [{}]}, "queries": {"value": {"path": []}}}
    UIAAdapter(profile, desktop=object()).preflight({"example"}, {"value"}, connect=False)


def test_discovery_retries_only_missing_observation(monkeypatch):
    from fakturama_cash import ui
    clock = Clock()
    monkeypatch.setattr(ui.time, "monotonic", clock.time)
    monkeypatch.setattr(ui.time, "sleep", clock.sleep)
    adapter = UIAAdapter({"timeout_seconds": 1}, desktop=object())
    attempts = []
    control = object()
    def observe(*_):
        attempts.append(None)
        if len(attempts) < 3:
            raise LookupError("not visible yet")
        return control
    monkeypatch.setattr(adapter, "_find_once", observe)
    assert adapter.find([{"title": "observed name"}], {}) is control
    assert len(attempts) == 3


def test_ambiguous_discovery_is_not_retried(monkeypatch):
    adapter = UIAAdapter({}, desktop=object())
    attempts = []
    def observe(*_):
        attempts.append(None)
        raise ReviewRequired("ambiguous")
    monkeypatch.setattr(adapter, "_find_once", observe)
    with pytest.raises(ReviewRequired, match="ambiguous"):
        adapter.find([{"title": "repeated label"}], {})
    assert len(attempts) == 1
