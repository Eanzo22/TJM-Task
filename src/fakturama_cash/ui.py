"""Calibrated UIA interaction. No coordinate constants or screenshot-specific offsets.

The profile is a local, reviewed mapping of semantic operations to observed controls.
Missing mappings fail preflight, before any business mutation. Profiles are not proof
of a successful live run; see docs/requirements.md for verification status.
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
            self.root()

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

    def _find_once(self, path, context):
        parent = self.root()
        if not path:
            raise ReviewRequired("Empty selector path", stage="UI discovery")
        for part in path:
            criteria = {k: resolve(v, context) for k, v in part.items()}
            allowed = {"title", "control_type", "auto_id"}
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
            if not matches:
                raise LookupError(criteria)
            if len(matches) != 1:
                raise ReviewRequired("Control is ambiguous", stage="UI discovery",
                                     expected=criteria, observed=len(matches))
            parent = matches[0]
        return parent

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

    def act(self, name, context):
        recipe = self.profile.get("actions", {}).get(name)
        if not recipe:
            raise ReviewRequired("Action not calibrated", stage=name)
        for step in recipe:
            control = self.find(step["path"], context)
            if not control.is_enabled():
                raise ReviewRequired("Target control disabled", stage=name)
            operation = step["operation"]
            value = resolve(step.get("value"), context)
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
        write_json(tree, nodes)
        root.capture_as_image().save(screenshot)
        return {"uia_tree": str(tree), "screenshot": str(screenshot), "kind": "live_capture"}


def load_profile(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
