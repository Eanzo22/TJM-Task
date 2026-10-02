"""Calibrated UIA interaction. No coordinate constants or screenshot-specific offsets.

The profile is a local, reviewed mapping of semantic operations to observed controls.
Missing mappings fail preflight, before any business mutation. Profiles are not proof
of a successful live run; see documents/implementation/requirements.md at the
workspace root for verification status.
"""
import json
import time
from pathlib import Path

from .errors import ReviewRequired
from .normalize import amount, day
from .state import write_json


def resolve(value, context):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        current = context
        for part in value[2:-1].split("."):
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current
    return value


def wait_stable(observe, *, timeout=10, interval=0.2, stable_for=0.6, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    previous = object()
    changed_at = clock()
    while clock() < deadline:
        current = observe()
        if current != previous:
            previous, changed_at = current, clock()
        elif clock() - changed_at >= stable_for:
            return current
        sleep(interval)
    raise ReviewRequired("UI did not reach a stable state before timeout", stage="wait", observed=repr(previous))


def _activate_capture_window(root):
    # UIA SetFocus can only warn when activation fails. Use the observed native
    # window handle to restore/raise the top-level window, then verify separately.
    from pywinauto.controls.hwndwrapper import HwndWrapper
    if not root.handle:
        raise ValueError("Diagnostic window has no native handle")
    HwndWrapper(root.handle).set_focus()


def _foreground_handle():
    from win32gui import GetForegroundWindow
    return GetForegroundWindow()


def _capture_state(root):
    rectangle = root.rectangle()
    bounds = (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom)
    ready = (bool(root.handle) and _foreground_handle() == root.handle
             and root.is_visible() and not root.is_minimized()
             and rectangle.width() > 0 and rectangle.height() > 0)
    return ready, bounds


def _wait_capture_ready(root, timeout):
    deadline = time.monotonic() + timeout
    previous = None
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        ready, bounds = _capture_state(root)
        if not ready or bounds != previous:
            previous = bounds if ready else None
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.3:
            return bounds
        time.sleep(0.1)
    raise ReviewRequired("Fakturama could not be brought to the foreground for capture",
                         stage="capture", next_action="Bring Fakturama to the front, leave it unobstructed, and rerun diagnose.")


class UIAAdapter:
    def __init__(self, profile, desktop=None):
        self.profile = profile
        if desktop is None:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
        self.desktop = desktop
        self.timeout = profile.get("timeout_seconds", 10)

    def root(self):
        candidates = self.desktop.windows(title_re=self.profile["window_title_re"], visible_only=True)
        if len(candidates) != 1:
            raise ReviewRequired("Expected exactly one Fakturama window", stage="UI discovery", observed=len(candidates))
        return candidates[0]

    def preflight(self, actions, queries, *, connect=True):
        missing = ["action:" + name for name in sorted(actions) if not self.profile.get("actions", {}).get(name)]
        missing += ["query:" + name for name in sorted(queries) if not self.profile.get("queries", {}).get(name)]
        if not self.profile.get("calibrated") or missing:
            raise ReviewRequired("UI profile is not fully calibrated", stage="UI preflight", observed=missing,
                                 next_action="Run diagnose, calibrate the missing controls/tables in a disposable workspace, and verify the profile.")
        if connect:
            self.prepare_window()

    def prepare_window(self):
        """Use one predictable layout; maximizing never saves business data."""
        root = self.root()
        _activate_capture_window(root)
        if not root.is_maximized():
            root.maximize()
        self._wait_for(lambda: root.is_maximized(), "Fakturama did not maximize")
        _wait_capture_ready(root, self.timeout)
        return root

    def _wait_for(self, observe, reason):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if observe():
                return
            time.sleep(0.1)
        raise ReviewRequired(reason, stage="UI navigation")

    def find(self, path, context):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                return self._find_once(path, context)
            except LookupError as exc:
                # Retry discovery only. The caller invokes its mutation once, after
                # a unique target exists; an uncertain click is never replayed.
                if time.monotonic() >= deadline:
                    raise ReviewRequired("Control did not appear before timeout", stage="UI discovery",
                                         expected=path) from exc
                time.sleep(0.2)

    def _find_once(self, path, context, parent=None):
        parent = self.root() if parent is None else parent
        if not path:
            raise ReviewRequired("Empty selector path", stage="UI discovery")
        for part in path:
            criteria = {k: resolve(v, context) for k, v in part.items()}
            allowed = {"title", "control_type", "auto_id", "to_right_of"}
            if not set(criteria) <= allowed or not criteria:
                raise ReviewRequired("Unsupported selector; use observed names/types/IDs", observed=criteria)
            matches = []
            for control in parent.descendants(**{k: v for k, v in criteria.items() if k == "control_type"}):
                info = control.element_info
                if "title" in criteria and info.name != criteria["title"]:
                    continue
                if "auto_id" in criteria and info.automation_id != criteria["auto_id"]:
                    continue
                if control.is_visible():
                    matches.append(control)
            if "to_right_of" in criteria:
                matches = self._right_of_label(parent, matches, criteria["to_right_of"])
            if not matches:
                raise LookupError(criteria)
            if len(matches) != 1:
                raise ReviewRequired("Control is ambiguous", stage="UI discovery",
                                     expected=criteria, observed=len(matches))
            parent = matches[0]
        return parent

    def _right_of_label(self, parent, controls, label):
        """Resolve unnamed fields from fresh label geometry, never SWT numeric IDs."""
        labels = [c for c in parent.descendants(control_type="Text")
                  if c.is_visible() and c.element_info.name == label]
        if len(labels) != 1:
            raise ReviewRequired("Field label is missing or ambiguous", stage="UI discovery", observed=label)
        anchor = labels[0].rectangle()
        candidates = []
        for control in controls:
            box = control.rectangle()
            if (box.width() > 0 and box.height() > 0 and box.left >= anchor.right
                    and anchor.top <= (box.top + box.bottom) / 2 <= anchor.bottom):
                candidates.append((box.left - anchor.right, control))
        if not candidates:
            return []
        nearest = min(distance for distance, _ in candidates)
        matches = [control for distance, control in candidates if distance == nearest]
        if len(matches) == 1:
            # If the intended field vanished, don't accidentally use a later
            # field on the same row (for example Date instead of Order number).
            edge = matches[0].rectangle().left
            for text in parent.descendants(control_type="Text"):
                box = text.rectangle()
                if (text.is_visible() and text.element_info.name and text.element_info.name != label
                        and anchor.right <= box.left < edge
                        and anchor.top <= (box.top + box.bottom) / 2 <= anchor.bottom):
                    raise ReviewRequired("Another label separates the target from its field", stage="UI discovery",
                                         expected=label, observed=text.element_info.name)
        return matches

    def _scalar(self, spec, context):
        control = self.find(spec["path"], context)
        mode = spec.get("read", "value")
        if mode == "toggle":
            state = control.get_toggle_state()
            if state not in (0, 1):
                raise ReviewRequired("Indeterminate checkbox", stage="read")
            value = state == 1
        elif mode == "text":
            value = control.window_text()
        elif control.element_info.control_type == "ComboBox":
            # ComboBoxWrapper has no get_value(). selected_text() reads the
            # selection (or UIA Value pattern) without opening the dropdown.
            # Never use window_text(): that can be the label, e.g. "VAT".
            try:
                value = control.selected_text()
            except Exception as exc:
                raise ReviewRequired("Cannot read dropdown selection", stage="read",
                                     next_action="Inspect the dropdown's accessible selection/value pattern.") from exc
            if value is None:
                raise ReviewRequired("Dropdown exposes no selected value", stage="read")
        else:
            value = control.get_value()
        if "transform" in spec:
            transform = spec["transform"]
            if transform == "decimal":
                value = str(amount(value))
            elif transform == "date":
                value = day(value).isoformat()
            elif transform == "blank-null":
                value = None if not value else value
            else:
                raise ReviewRequired("Unknown read transform", observed=transform)
        return value

    def _read(self, spec, context):
        # A nested field group may live on a different tab. Preparation is
        # navigation-only and idempotent, so repeated snapshots never save/edit.
        for step in spec.get("prepare", []):
            self._navigate_control(step, context)
        if "fields" in spec:
            return {name: self._read(field, context) for name, field in spec["fields"].items()}
        if "rows" in spec:
            table = self.find(spec["path"], context)
            rows = table.descendants(control_type=spec["rows"].get("control_type", "DataItem"))
            if not rows:
                # Empty UIA children do not prove that a custom SWT table is empty.
                if "empty_indicator" not in spec:
                    raise ReviewRequired("Table exposes no accessible rows and has no calibrated empty indicator", stage="table_read")
                indicator = self._scalar(spec["empty_indicator"], context)
                if indicator != spec["empty_text"]:
                    raise ReviewRequired("Cannot distinguish empty from inaccessible table", stage="table_read")
                return []
            result = []
            for row in rows:
                cells = row.children()
                item = {}
                for name, observed_name in spec["rows"]["columns"].items():
                    candidates = [c for c in cells if c.element_info.name == observed_name]
                    if len(candidates) != 1:
                        raise ReviewRequired("Grid cells require calibration", stage="table_read", observed=name)
                    item[name] = candidates[0].get_value()
                result.append(item)
            # Reading only visible/virtualized rows could create duplicates. A calibrated
            # count control must prove that the complete result set was enumerated.
            if "total_count" not in spec or int(self._scalar(spec["total_count"], context)) != len(result):
                raise ReviewRequired("Cannot prove all result rows were read", stage="table_read")
            return result
        if "values" in spec:
            control = self.find(spec["path"], context)
            return [c.window_text() for c in control.descendants(control_type=spec["values"])]
        return self._scalar(spec, context)

    def read(self, name, context):
        spec = self.profile.get("queries", {}).get(name)
        if not spec:
            raise ReviewRequired("Query not calibrated", stage=name)
        return wait_stable(lambda: self._read(spec, context), timeout=self.timeout)

    def _navigate_control(self, step, context):
        operation = step.get("operation")
        try:
            if operation == "select_tab":
                tab = self.find(step["path"], context)
                if tab.element_info.control_type != "TabItem" or not tab.is_enabled():
                    raise ReviewRequired("select_tab requires an enabled, scoped TabItem", stage="UI navigation")
                if not tab.is_selected():
                    tab.select()
                # Re-find after selection: nested panels may rebuild their controls.
                self._wait_for(lambda: self.find(step["path"], context).is_selected(),
                               "Requested tab did not become selected")
                return
            if operation != "scroll_to":
                raise ReviewRequired("Query preparation supports only select_tab/scroll_to", stage="UI navigation")
            direction = step.get("direction", "down")
            limit = step.get("max_steps", 8)
            if direction not in ("up", "down", "left", "right") or type(limit) is not int or not 1 <= limit <= 30:
                raise ReviewRequired("Invalid bounded scroll configuration", stage="UI navigation")
            deadline = time.monotonic() + self.timeout
            for index in range(limit + 1):
                panel = self.find(step["path"], context)
                try:
                    # Target path is RELATIVE to this panel. A similarly named
                    # field elsewhere must not end the search in the wrong pane.
                    target = self._find_once(step["target_path"], context, parent=panel)
                    outer, inner = panel.rectangle(), target.rectangle()
                    if (inner.width() > 0 and inner.height() > 0 and
                            outer.left <= inner.left < inner.right <= outer.right and
                            outer.top <= inner.top < inner.bottom <= outer.bottom):
                        return
                except LookupError:
                    pass  # Off-screen is not missing data; continue bounded navigation.
                if index == limit or time.monotonic() >= deadline:
                    break
                axis = "CurrentVerticalScrollPercent" if direction in ("up", "down") else "CurrentHorizontalScrollPercent"
                before = getattr(panel.iface_scroll, axis)
                if before < 0 or (before == 0 and direction in ("up", "left")) or (before == 100 and direction in ("down", "right")):
                    break
                # Scroll the observed panel, not the desktop or guessed wheel coordinates.
                panel.scroll(direction, "page", count=1)
                while time.monotonic() < deadline:
                    fresh = self.find(step["path"], context)
                    if getattr(fresh.iface_scroll, axis) != before:
                        break
                    time.sleep(0.1)
                else:
                    break
            raise ReviewRequired("Scroll target not visible within the configured limit", stage="UI navigation",
                                 expected=step["target_path"], next_action="Inspect the panel/tab mapping; do not assume an unreadable field or table is empty.")
        except ReviewRequired:
            raise
        except Exception as exc:
            # Some SWT panels lack UIA Scroll/Selection patterns. Stop rather
            # than introducing an uncalibrated keyboard or coordinate fallback.
            raise ReviewRequired("Navigation pattern unavailable or failed", stage="UI navigation",
                                 observed=str(exc), next_action="Calibrate this tab/panel using live evidence.") from exc

    def act(self, name, context):
        recipe = self.profile.get("actions", {}).get(name)
        if not recipe:
            raise ReviewRequired("Action not calibrated", stage=name)
        for step in recipe:
            if step["operation"] in ("select_tab", "scroll_to"):
                self._navigate_control(step, context)
                if step.get("wait_query"):
                    self.read(step["wait_query"], context)
                continue
            control = self.find(step["path"], context)
            if not control.is_enabled():
                raise ReviewRequired("Target control disabled", stage=name)
            operation = step["operation"]
            value = resolve(step.get("value"), context)
            if "format" in step:
                if operation != "set" or step["format"] != "date_english":
                    raise ReviewRequired("Unsupported UI write format", stage=name)
                # Match the observed English named-month editor without relying
                # on the OS locale. Read-back still normalizes to an ISO date.
                parsed = day(value)
                month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[parsed.month - 1]
                value = f"{month} {parsed.day}, {parsed.year}"
            if operation == "invoke":
                control.invoke()
            elif operation == "select":
                control.select() if value is None else control.select(str(value))
            elif operation == "set":
                control.set_edit_text(str(value))
            elif operation == "toggle":
                if not isinstance(value, bool):
                    raise ReviewRequired("Checkbox target must be boolean", stage=name)
                if control.get_toggle_state() != int(value):
                    control.toggle()
            elif operation == "click_bounds":
                # For a UIA-exposed control without Invoke: use its fresh current bounds.
                rectangle = control.rectangle()
                control.click_input(coords=(rectangle.width() // 2, rectangle.height() // 2))
            else:
                raise ReviewRequired("Unsupported UI operation", stage=name, observed=operation)
            if step.get("wait_query"):
                self.read(step["wait_query"], context)

    def capture(self, directory, label):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        root = self.root()
        try:
            root = self.prepare_window()
            bounds = _wait_capture_ready(root, self.timeout)
        except ReviewRequired:
            raise
        except Exception as exc:
            raise ReviewRequired("Could not activate Fakturama for diagnostic capture",
                                 stage="capture", observed=str(exc),
                                 next_action="Bring Fakturama to the front and rerun diagnose; no screenshot was saved.") from exc
        nodes = []
        for element in [root, *root.descendants()]:
            info = element.element_info
            node = {"name": info.name, "type": info.control_type, "auto_id": info.automation_id,
                          "parent_name": element.parent().element_info.name if element.parent() else None,
                          "rectangle": str(element.rectangle())}
            try:
                node["value"] = element.iface_value.CurrentValue
            except Exception:
                pass  # Most layout containers correctly expose no Value pattern.
            try:
                node["toggle"] = element.get_toggle_state()
            except Exception:
                pass
            nodes.append(node)
        tree = directory / (label + "-uia.json")
        screenshot = directory / (label + ".png")
        # capture_as_image reads desktop pixels in this rectangle, NOT a hidden
        # window surface. Never label a screenshot as Fakturama if focus changed
        # during slow UIA enumeration or while the pixels were being captured.
        if _capture_state(root) != (True, bounds):
            raise ReviewRequired("Fakturama focus or bounds changed before capture", stage="capture",
                                 next_action="Keep Fakturama in front and stationary until diagnose finishes.")
        captured = root.capture_as_image()
        if (_capture_state(root) != (True, bounds) or self.root().handle != root.handle):
            raise ReviewRequired("Fakturama focus or bounds changed during capture; image discarded",
                                 stage="capture", next_action="Keep Fakturama in front and rerun diagnose.")
        if captured is None or captured.size != (bounds[2] - bounds[0], bounds[3] - bounds[1]):
            raise ReviewRequired("Diagnostic image dimensions do not match the target window", stage="capture")
        # Save only after all guards pass. A failed attempt must not replace a
        # previous valid screenshot with VS Code or another foreground window.
        write_json(tree, nodes)
        captured.save(screenshot)
        metadata = directory / (label + "-capture.json")
        write_json(metadata, {"window_title": root.window_text(), "window_handle": root.handle,
                              "bounds": list(bounds), "capture_method": "foreground_screen_region",
                              "foreground_verified_before_and_after": True})
        return {"uia_tree": str(tree), "screenshot": str(screenshot),
                "capture_metadata": str(metadata), "kind": "live_capture"}


def load_profile(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
