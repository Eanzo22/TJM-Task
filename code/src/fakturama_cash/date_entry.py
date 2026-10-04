"""Guarded keyboard entry for the observed English Nebula date editor."""
import re
import time
from datetime import date

from .errors import ReviewRequired


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PATTERN = re.compile(r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2}) (?P<day>\d{1,2}), (?P<year>\d{4})")


def date_text(control):
    # SWT exposes the date as Value, with an empty accessible Name.
    return control.window_text() or control.get_value()


def observe_date(control):
    """Identify the highlighted segment from accessible character offsets."""
    text = date_text(control)
    match = PATTERN.fullmatch(text)
    if not match:
        raise ReviewRequired("Unsupported date display format", stage="date entry", observed=text)
    try:
        month = match["month"]
        value = date(int(match["year"]), int(month) if month.isdigit() else MONTHS.index(month) + 1,
                     int(match["day"]))
        try:
            selection = tuple(control.selection_indices())
        except Exception:
            # CDateTime's native Edit lacks UIA TextPattern. EM_GETSEL reads
            # the visible selection on that same UIA-discovered control; all
            # actual date changes still use the widget's keyboard handling.
            if not getattr(control, "handle", None) or control.class_name() != "Edit":
                raise
            from pywinauto.controls.win32_controls import EditWrapper
            native = EditWrapper(control.handle)
            if native.window_text() != text:
                raise ValueError("Date text changed while reading selection")
            selection = tuple(native.selection_indices())
    except Exception as exc:
        raise ReviewRequired("Cannot read date value or selected segment", stage="date entry", observed=text) from exc
    segment = next((name for name in ("month", "day", "year") if selection == match.span(name)), None)
    return value, segment


def enter_date(control, target, *, focus_is_safe, timeout):
    """Send only digits/arrows to a verified focused field; never paste or press Save."""
    from .normalize import day
    # Do not disturb an already-correct date just to exercise segment entry.
    # The adapter still blurs and verifies the retained value afterwards.
    try:
        if day(date_text(control)) == target:
            return
    except (ValueError, TypeError):
        pass  # The segment observer below reports the unsupported display.
    def send(key):
        # type_keys sends OS keyboard input, so verify both window ownership and
        # field focus before EVERY key. Never auto-refocus after a lost focus.
        if not focus_is_safe():
            raise ReviewRequired("Date keyboard focus or foreground window changed", stage="date entry")
        control.type_keys(key, set_foreground=False, vk_packet=False, turn_off_numlock=False, pause=0.05)
        if not focus_is_safe():
            raise ReviewRequired("Date keyboard focus changed during entry", stage="date entry")

    current, _ = observe_date(control)  # Require readable selection support before any key.
    # Day 1 is a safe intermediate when moving from Jan 31 to February or
    # changing the year of Feb 29. Verify it like every other intentional edit.
    for name, number in (("day", 1), ("year", target.year), ("month", target.month), ("day", target.day)):
        if getattr(current, name) == number:
            continue
        for attempt in range(4):
            seen, selected = observe_date(control)
            if seen != current:
                raise ReviewRequired("Date changed unexpectedly during segment navigation", stage="date entry",
                                     expected=current.isoformat(), observed=seen.isoformat())
            if selected == name:
                break
            if attempt == 3:
                raise ReviewRequired("Could not select date segment", stage="date entry", expected=name, observed=selected)
            send("{RIGHT}")
            deadline = time.monotonic() + timeout
            while observe_date(control)[1] == selected:
                if time.monotonic() >= deadline:
                    raise ReviewRequired("Date segment navigation did not advance", stage="date entry", expected=name)
                time.sleep(0.05)
        # Two digits (four for year) commit and auto-advance in CDateTime. Do not
        # append an extra arrow or Enter: that may skip a segment or invoke UI.
        for digit in f"{number:0{4 if name == 'year' else 2}d}":
            send(digit)
        expected = current.replace(**{name: number})
        deadline = time.monotonic() + timeout
        while True:
            observed, _ = observe_date(control)
            if observed == expected:
                break
            if time.monotonic() >= deadline:
                raise ReviewRequired("Date segment was not retained", stage="date entry",
                                     expected=expected.isoformat(), observed=observed.isoformat())
            time.sleep(0.05)
        current = expected
