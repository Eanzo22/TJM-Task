"""Calibrated UIA interaction. No coordinate constants or screenshot-specific offsets.

The profile is a local, reviewed mapping of semantic operations to observed controls.
Missing mappings fail preflight, before any business mutation. Profiles are not proof
of a successful live run; see documents/implementation/requirements.md at the
workspace root for verification status.
"""
import json
import re
import time
from pathlib import Path

from .errors import ReviewRequired
from .normalize import amount, day, key
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


def _matching_window_handles(pattern):
    """Filter native top-level titles before asking UIA to inspect controls."""
    from win32gui import EnumWindows, GetWindowText, IsWindowVisible
    matches = []
    def collect(handle, _):
        if IsWindowVisible(handle) and re.match(pattern, GetWindowText(handle)):
            matches.append(handle)
    EnumWindows(collect, None)
    return matches


def _click_control(control, *, relative=None, double=False):
    """Bring the observed control's own window forward before a bounds click."""
    from win32gui import GetAncestor, WindowFromPoint, IsWindowEnabled
    from win32process import GetWindowThreadProcessId
    from pywinauto.controls.hwndwrapper import HwndWrapper
    ancestor = control
    while ancestor is not None and not ancestor.handle:
        ancestor = ancestor.parent()
    if ancestor is None:
        raise ReviewRequired("Click target has no native window", stage="UI navigation")
    window = GetAncestor(ancestor.handle, 2)  # GA_ROOT, not a modal's owner.
    HwndWrapper(window).set_focus()
    box = control.rectangle()
    point = ((box.left + box.right) // 2, (box.top + box.bottom) // 2) if relative is None else (box.left + relative[0], box.top + relative[1])
    if (not IsWindowEnabled(window) or not control.is_enabled() or box.width() <= 0 or box.height() <= 0
            or not (box.left <= point[0] < box.right and box.top <= point[1] < box.bottom)
            or _foreground_handle() != window
            or GetAncestor(WindowFromPoint(point), 2) != window
            or GetWindowThreadProcessId(WindowFromPoint(point))[1] != control.process_id()):
        raise ReviewRequired("Click target is blocked or obscured", stage="UI navigation")
    control.click_input(coords=point, absolute=True, double=double)


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
        self._native_discovery = desktop is None
        if desktop is None:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
        self.desktop = desktop
        self.timeout = profile.get("timeout_seconds", 10)
        self._table_reads = {}
        self._root_control = None
        self._root_title = None

    def root(self):
        # UIA can report the application's root as off-screen while minimized.
        # Native visibility still identifies its real top-level window, allowing
        # prepare_window to restore it before any input or screenshot capture.
        from win32gui import IsWindow, IsWindowVisible
        if self._root_control is not None:
            window = self._root_control
            if (not IsWindow(window.handle) or not IsWindowVisible(window.handle)
                    or window.window_text() != self._root_title):
                raise ReviewRequired("Bound Fakturama window closed or changed", stage="UI discovery")
            return window
        if self._native_discovery:
            handles = _matching_window_handles(self.profile["window_title_re"])
            candidates = [self.desktop.window(handle=handle).wrapper_object() for handle in handles]
        else:
            candidates = [window for window in self.desktop.windows(
                title_re=self.profile["window_title_re"], visible_only=False)
                if window.handle and IsWindowVisible(window.handle)]
        if len(candidates) != 1:
            raise ReviewRequired("Expected exactly one Fakturama window", stage="UI discovery", observed=len(candidates))
        # Bind once per adapter/run. Re-enumerating every application's UIA tree
        # on every field/key is slow and can exhaust the observation timeout.
        # Descendant controls are still reacquired; never retarget another window
        # automatically after this one closes.
        self._root_control = candidates[0]
        self._root_title = candidates[0].window_text()
        return self._root_control

    def preflight(self, actions, queries, *, connect=True):
        missing = ["action:" + name for name in sorted(actions) if not self.profile.get("actions", {}).get(name)]
        missing += ["query:" + name for name in sorted(queries) if not self.profile.get("queries", {}).get(name)]
        if not self.profile.get("calibrated") or missing:
            raise ReviewRequired("UI profile is not fully calibrated", stage="UI preflight", observed=missing,
                                 next_action="Run diagnose, calibrate the missing controls/tables in a disposable workspace, and verify the profile.")
        from .clipboard_table import validate_copy_config
        for query in queries:
            spec = self.profile["queries"][query]
            if "clipboard_rows" in spec:
                validate_copy_config(spec["clipboard_rows"])
        if connect:
            root = self.prepare_window()
            dirty = [tab.element_info.name for tab in root.descendants(control_type="TabItem")
                     if tab.element_info.name.startswith("*")]
            if dirty:
                raise ReviewRequired("Unsaved editors are open", stage="UI preflight", observed=dirty,
                                     next_action="Resolve existing unsaved editors before starting a new transaction.")

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
        for position, part in enumerate(path):
            criteria = {k: resolve(v, context) for k, v in part.items()}
            allowed = {"title", "control_type", "auto_id", "to_right_of", "below_label", "leaf", "selected", "direct"}
            if not set(criteria) <= allowed or not criteria:
                raise ReviewRequired("Unsupported selector; use observed names/types/IDs", observed=criteria)
            matches = []
            if 'direct' in criteria and criteria['direct'] is not True:
                raise ReviewRequired("direct selector must be true", stage="UI discovery")
            candidates = (parent.children() if criteria.get('direct') else
                          parent.descendants(**{k: v for k, v in criteria.items() if k == "control_type"}))
            native_modal = (self._native_discovery and position == 0
                            and criteria.get('control_type') == 'Window' and 'title' in criteria)
            if native_modal:
                # SWT sometimes parents a dialog under a hidden Shell, outside
                # the main UIA tree. Bind its observed native title to this same
                # process, retaining the original workspace/window binding.
                from win32process import GetWindowThreadProcessId
                handles = _matching_window_handles('^' + re.escape(criteria['title']) + '$')
                candidates = [self.desktop.window(handle=h).wrapper_object() for h in handles
                              if GetWindowThreadProcessId(h)[1] == self.root().process_id()]
            for control in candidates:
                info = control.element_info
                if 'control_type' in criteria and info.control_type != criteria['control_type']:
                    continue
                if "title" in criteria and info.name != criteria["title"]:
                    continue
                if "auto_id" in criteria and info.automation_id != criteria["auto_id"]:
                    continue
                if "leaf" in criteria:
                    if criteria["leaf"] is not True:
                        raise ReviewRequired("leaf selector must be true", stage="UI discovery")
                    if control.descendants():
                        continue
                if "selected" in criteria:
                    if criteria["selected"] is not True or info.control_type != "TabItem":
                        raise ReviewRequired("selected selector requires a TabItem", stage="UI discovery")
                    if not control.is_selected():
                        continue
                if native_modal or control.is_visible():
                    matches.append(control)
            if "to_right_of" in criteria:
                matches = self._right_of_label(parent, matches, criteria["to_right_of"], context)
            if "below_label" in criteria:
                matches = self._below_label(parent, matches, criteria["below_label"], context)
            if not matches:
                raise LookupError(criteria)
            if len(matches) != 1:
                raise ReviewRequired("Control is ambiguous", stage="UI discovery",
                                     expected=criteria, observed=len(matches))
            parent = matches[0]
        return parent

    def _right_of_label(self, parent, controls, label, context=None):
        """Resolve unnamed fields from fresh label geometry, never SWT numeric IDs."""
        # Compound labels (First Name Last Name, ZIP - City) have two fields.
        # The second field can anchor to the first field's scoped selector.
        labels = ([self._find_once([label], context or {}, parent=parent)] if isinstance(label, dict)
                  else [c for c in parent.descendants(control_type="Text")
                        if c.is_visible() and c.element_info.name == label])
        if len(labels) != 1:
            raise ReviewRequired("Field label is missing or ambiguous", stage="UI discovery", observed=label)
        anchor = labels[0].rectangle()
        candidates = []
        for control in controls:
            box = control.rectangle()
            aligned_y = box.top if control.element_info.control_type == 'Pane' else (box.top + box.bottom) / 2
            if (box.width() > 0 and box.height() > 0 and box.left >= anchor.right
                    and anchor.top <= aligned_y <= anchor.bottom):
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

    def _below_label(self, parent, controls, label, context=None):
        """Resolve the nearest control below a label using current UIA bounds."""
        labels = ([self._find_once([label], context or {}, parent=parent)] if isinstance(label, dict)
                  else [c for c in parent.descendants(control_type="Text")
                        if c.is_visible() and c.element_info.name == label])
        if len(labels) != 1:
            raise ReviewRequired("Field label is missing or ambiguous", stage="UI discovery", observed=label)
        anchor = labels[0].rectangle()
        candidates = []
        for control in controls:
            box = control.rectangle()
            if (box.width() > 0 and box.height() > 0 and box.top >= anchor.bottom
                    and box.left < anchor.right and box.right > anchor.left):
                candidates.append((box.top - anchor.bottom, control))
        if not candidates:
            return []
        nearest = min(distance for distance, _ in candidates)
        return [control for distance, control in candidates if distance == nearest]

    def _scalar(self, spec, context):
        control = self.find(spec["path"], context)
        mode = spec.get("read", "value")
        if mode == "toggle":
            state = control.get_toggle_state()
            if state not in (0, 1):
                raise ReviewRequired("Indeterminate checkbox", stage="read")
            value = state == 1
        elif mode == "options":
            value = self._combo_options(control)
        elif mode == "native_text":
            # SWT search Edit's UIA Value becomes blank on blur even though
            # its native text and active filter are retained. Read the same
            # UIA-discovered HWND, never a guessed handle or application data.
            if (control.element_info.control_type != "Edit" or not control.handle
                    or control.class_name() != "Edit"):
                raise ReviewRequired("Native text read requires an observed Windows Edit", stage="read")
            from pywinauto.controls.hwndwrapper import HwndWrapper
            value = HwndWrapper(control.handle).window_text()
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
            elif transform == "vat_code":
                value = self._vat_code(value)
            elif transform == 'currency':
                if not re.search(r'(?:EUR|€)\s*$', value):
                    raise ReviewRequired('Document currency is not visibly EUR', stage='environment')
                value = 'EUR'
            else:
                raise ReviewRequired("Unknown read transform", observed=transform)
        return value

    def _read(self, spec, context):
        if spec.get('initial_draft') and context.get('order_tab') == 'New Order':
            return self._read(self.profile['queries'][spec['initial_draft']], context)
        if spec.get('debtor_form') is True:
            from .master_forms import debtor_values
            return debtor_values(self, context)
        if 'if_present' in spec:
            try:
                self._find_once(spec['if_present'], context)
            except LookupError:
                return self._read(self.profile['queries'][spec['fallback_query']], context)
        # A nested field group may live on a different tab. Preparation is
        # navigation-only and idempotent, so repeated snapshots never save/edit.
        for step in spec.get("prepare", []):
            self._navigate_control(step, context)
        if 'when_checked' in spec and not self._read(spec['when_checked'], context):
            return None
        if 'address_structure' in spec:
            from .document_fields import read_address
            return read_address(self._scalar(spec, context), resolve(spec['address_structure'], context),
                                contact=context.get('selected_debtor'))
        if 'merge_queries' in spec:
            result = {}
            for query in spec['merge_queries']:
                result.update(self._read(self.profile['queries'][query], context))
            return result
        if 'concat_queries' in spec:
            rows = []
            for query in spec['concat_queries']:
                rows.extend(self._read(self.profile['queries'][query], context))
            identities = [(row['type'], row['no']) for row in rows]
            if len(set(identities)) != len(identities):
                raise ReviewRequired('Document appears in multiple categories', stage='documents_read')
            return rows
        if "fields" in spec:
            return {name: self._read(field, context) for name, field in spec["fields"].items()}
        if "same_text" in spec:
            pair = spec["same_text"]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ReviewRequired("same_text requires two UI observations", stage="read")
            values = [self._read(part, context) for part in pair]
            if not all(isinstance(value, str) for value in values):
                raise ReviewRequired("same_text requires text observations", stage="read")
            return key(values[0]) == key(values[1])
        if "clipboard_rows" in spec:
            rows = self._read_copied_rows(spec, context)
            if spec.get('row_transform') == 'order_item':
                from .item_table import item_values
                rows = [item_values(row) for row in rows]
            elif spec.get('row_transform') == 'document':
                from .document_fields import document_values
                rows = [document_values(row) for row in rows]
            if 'row_index' in spec:
                index = resolve(spec['row_index'], context)
                if type(index) is not int or not 0 <= index < len(rows):
                    raise ReviewRequired('Requested item row is missing', stage='item_read')
                return rows[index]
            return rows
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
        result = wait_stable(lambda: self._read(spec, context), timeout=self.timeout)
        if "clipboard_rows" in spec and 'row_index' not in spec and 'row_transform' not in spec:
            # Selection only accepts a snapshot issued by this adapter, not an
            # index supplied by the caller or guessed from the input order.
            from .clipboard_table import table_fingerprint
            fingerprint = table_fingerprint(result)
            self._table_reads[name] = fingerprint
            return [dict(row, _ui_row={"query": name, "index": i, "fingerprint": fingerprint})
                    for i, row in enumerate(result)]
        return result

    def _keyboard_safe(self, control):
        from win32process import GetWindowThreadProcessId
        from win32gui import GetAncestor
        # Owned selector dialogs have their own foreground HWND. Requiring the
        # main HWND would incorrectly reject them; field focus plus process
        # ownership binds input to the discovered control in either window.
        same_window = (not getattr(control,'handle',None) or
                       GetAncestor(_foreground_handle(),2) == GetAncestor(control.handle,2))
        focused = control.has_keyboard_focus()
        if same_window and getattr(control,'handle',None):
            from pywinauto.controls.hwndwrapper import HwndWrapper
            from win32gui import IsChild
            native = HwndWrapper(control.handle).get_focus()
            focused = native is not None and (native.handle == control.handle or
                (control.element_info.control_type=='ComboBox' and IsChild(control.handle,native.handle)))
        return (same_window and control.is_enabled() and focused
                and GetWindowThreadProcessId(_foreground_handle())[1] == control.process_id())

    def inspect_table(self, name):
        """Copy for calibration only; never issue a row-selection token."""
        spec = self.profile.get("queries", {}).get(name, {})
        if "clipboard_rows" not in spec:
            raise ReviewRequired("Table copy query missing", stage="table_read")
        return wait_stable(lambda: self._read_copied_rows(spec, {}, allow_unverified=True), timeout=self.timeout)

    def _read_copied_rows(self, spec, context, *, allow_unverified=False):
        from .clipboard_table import copy_table, parse_table, validate_copy_config, snapshot_fingerprint
        config = spec["clipboard_rows"]
        validate_copy_config(config, allow_unverified=allow_unverified)
        # all_rows is a calibration claim about Ctrl+A/Ctrl+C, not a heuristic:
        # it must include off-screen rows and columns. A visible-only copy is
        # never sufficient to decide that a master record is missing.
        table = self.find(spec["path"], context)
        identity = tuple(table.element_info.runtime_id)
        count = None
        if "total_count" in spec:
            raw = str(self._scalar(spec["total_count"], context))
            if not raw.isascii() or not raw.isdecimal():
                raise ReviewRequired("Invalid table result count", stage="table_read", observed=raw)
            count = int(raw)
        empty = ("empty_indicator" in spec and "empty_text" in spec
                 and self._scalar(spec["empty_indicator"], context) == spec["empty_text"])
        if "empty_snapshot" in config:
            # NatTable throws an internal error when Copy has no selected cells.
            # A calibrated exact empty-grid image is an alternative to an
            # accessible empty label. Return to the first row before comparing;
            # never interpret a failed Copy or an unreadable table as empty.
            from .clipboard_table import focus_table
            focus_table(table,lambda:self._keyboard_safe(table))
            if not self._keyboard_safe(table):
                raise ReviewRequired("Table focus changed before empty-state check", stage="table_read")
            table.type_keys("^{HOME}", set_foreground=False, pause=0.05)
            if not self._keyboard_safe(table):
                raise ReviewRequired("Table focus changed during empty-state check", stage="table_read")
            expected = config["empty_snapshot"]
            image = table.capture_as_image()
            if config.get('empty_crop'):
                if image.width < expected['width'] or image.height < expected['height']:
                    raise ReviewRequired('Empty grid crop no longer fits', stage='table_read')
                # The calibrated item area remains anchored on the left when
                # its editor gains unused space on the right.
                image = image.crop((0,0,expected['width'],expected['height']))
            snapshot = snapshot_fingerprint(image)
            if any(snapshot[k] != expected[k] for k in ("width", "height")):
                raise ReviewRequired("Table layout changed since empty-state calibration", stage="table_read")
            empty = empty or snapshot == expected
            if tuple(self.find(spec["path"], context).element_info.runtime_id) != identity:
                raise ReviewRequired("Table was replaced during empty-state check", stage="table_read")
        # An explicit empty indicator avoids copying when a grid's Copy command
        # intentionally does nothing for zero rows. A count must agree if present.
        if empty:
            if count not in (None, 0):
                raise ReviewRequired("Empty indicator conflicts with table count", stage="table_read")
            return []
        if 'row_walk' in config:
            from .clipboard_table import walk_table
            # A fresh Contact dialog has no selected row. Ctrl+Home alone does
            # not initialize it; Copy then raises copiedCells=null. Select the
            # first observed row once before the bounded walk (no activation).
            geometry = config['row_geometry']
            image = table.capture_as_image()
            y = geometry['header_height'] + geometry['row_height'] // 2
            if image.width != geometry['width'] or y >= image.height:
                raise ReviewRequired('Contact grid layout changed', stage='table_read')
            _click_control(table, relative=(geometry['column_x'], y))
            rows = walk_table(table, config, is_safe=lambda: self._keyboard_safe(table), timeout=self.timeout)
            if count is not None and len(rows) != count:
                raise ReviewRequired("Walked row count does not match result count", stage="table_read")
        else:
            text = copy_table(table, is_safe=lambda: self._keyboard_safe(table), timeout=self.timeout)
            rows = parse_table(text, config["columns"], headers=config.get("headers"), expected_count=count,
                               format=config.get("format", "quoted_tsv"))
        if tuple(self.find(spec["path"], context).element_info.runtime_id) != identity:
            raise ReviewRequired("Table was replaced during copy", stage="table_read")
        return [dict(row, _table_id=list(identity)) for row in rows]

    def _select_copied_row(self, step, context):
        from .clipboard_table import table_fingerprint
        selected = resolve(step.get("value"), context)
        token = selected.get("_ui_row", {}) if isinstance(selected, dict) else {}
        query, index = token.get("query"), token.get("index")
        spec = self.profile.get("queries", {}).get(query, {})
        if (not token or self._table_reads.get(query) != token.get("fingerprint")
                or not spec.get("clipboard_rows") or type(index) is not int
                or step.get("query") != query):
            raise ReviewRequired("Row selection requires a current table observation", stage="table_select")
        # Recopy the complete table before positioning. Changed search results,
        # row ordering, replacement dialogs and duplicate rows remain visible.
        fresh = wait_stable(lambda: self._read(spec, context), timeout=self.timeout)
        if (table_fingerprint(fresh) != token["fingerprint"] or not 0 <= index < len(fresh)
                or fresh[index] != {k: v for k, v in selected.items() if k != "_ui_row"}):
            raise ReviewRequired("Table changed since row matching", stage="table_select")
        mode = spec["clipboard_rows"].get("keyboard_selection")
        if mode not in ("ctrl_home_down_enter", "ctrl_home_down_double_click", "ctrl_home_down_confirm"):
            raise ReviewRequired("Table keyboard row selection is not calibrated", stage="table_select")
        if mode == "ctrl_home_down_confirm" and not step.get("confirm_path"):
            raise ReviewRequired("Row selection needs an explicit confirmation control", stage="table_select")
        table = self.find(spec["path"], context)
        if list(table.element_info.runtime_id) != fresh[index]["_table_id"]:
            raise ReviewRequired("Table was replaced before selection", stage="table_select")
        # Consume before sending any positioning/activation keys. An uncertain
        # outcome cannot be replayed with the same observation token.
        del self._table_reads[query]
        keys = ["^{HOME}", *(["{DOWN}"] * index)]
        if mode == "ctrl_home_down_enter":
            keys.append("{ENTER}")
        for key in keys:
            if not self._keyboard_safe(table):
                raise ReviewRequired("Table focus changed before selection", stage="table_select")
            table.type_keys(key, set_foreground=False, pause=0.05)
        if mode in ("ctrl_home_down_double_click", "ctrl_home_down_confirm"):
            from .clipboard_table import copy_table, parse_table, header_matches
            # Verify the one positioned row through Copy before any activation.
            text = copy_table(table, is_safe=lambda: self._keyboard_safe(table), timeout=self.timeout, select_all=False)
            config = spec["clipboard_rows"]
            row = parse_table(text, config["columns"], headers=config.get("headers"), expected_count=1,
                              format=config.get("format", "quoted_tsv"))[0]
            if row != {k: v for k, v in fresh[index].items() if k != "_table_id"}:
                raise ReviewRequired("Keyboard selected a different table row", stage="table_select")
            if mode == "ctrl_home_down_confirm":
                confirm = self.find(step['confirm_path'], context)
                if not confirm.is_enabled() or not self._keyboard_safe(table):
                    raise ReviewRequired("Row confirmation is unavailable or focus changed", stage="table_select")
                if list(self.find(spec['path'], context).element_info.runtime_id) != fresh[index]['_table_id']:
                    raise ReviewRequired("Table was replaced before confirmation", stage="table_select")
                confirm.invoke()
                return
            geometry = config["row_geometry"]
            screenshot = table.capture_as_image()
            header = screenshot.crop((0, 0, screenshot.width, geometry["header_height"]))
            bottom = geometry["header_height"] + (index + 1) * geometry["row_height"]
            limit = screenshot.height
            for bar in table.descendants(control_type="ScrollBar"):
                if bar.is_visible() and bar.window_text() == "Horizontal":
                    limit = min(limit, bar.rectangle().top - table.rectangle().top)
            if (screenshot.width != geometry["width"] or bottom > limit
                    or not header_matches(header, geometry['header_sha256'])):
                raise ReviewRequired("Row is off-screen or table layout changed", stage="table_select")
            if not self._keyboard_safe(table):
                raise ReviewRequired("Table focus changed before activation", stage="table_select")
            if list(self.find(spec["path"], context).element_info.runtime_id) != fresh[index]['_table_id']:
                raise ReviewRequired("Table was replaced before activation", stage="table_select")
            _click_control(table, relative=(geometry["column_x"], bottom - geometry["row_height"] // 2), double=True)

    def _type_text(self, step, context, value, *, verify_after_blur=True):
        """Use SWT keyboard/modify events where UIA SetValue does not persist."""
        text = "" if value is None else str(value)
        if any(ord(c) < 32 for c in text) or not step.get("commit_path") or step["commit_path"] == step["path"]:
            raise ReviewRequired("Text entry needs plain text and a separate commit field", stage="text entry")
        if "transform" in step and step["transform"] != "decimal":
            raise ReviewRequired("Unsupported text read-back transform", stage="text entry")
        if step.get("read", "value") not in ("value", "native_text"):
            raise ReviewRequired("Unsupported text read-back mode", stage="text entry")
        expected = str(amount(text)) if step.get("transform") == "decimal" else text
        if "decimal_separator" in step:
            if step.get("transform") != "decimal" or step["decimal_separator"] not in (".", ","):
                raise ReviewRequired("Invalid decimal keyboard format", stage="text entry")
            text = expected.replace(".", step["decimal_separator"])
        control, commit = self.find(step["path"], context), self.find(step["commit_path"], context)
        if control.element_info.control_type != "Edit" or not commit.is_enabled():
            raise ReviewRequired("Text entry requires an Edit and enabled commit field", stage="text entry")
        control.set_focus()
        if not self._keyboard_safe(self.find(step['path'], context)):
            # SWT can leave focus in the navigation view after SetFocus. Click
            # the freshly observed Edit, then verify focus before any text keys.
            _click_control(self.find(step['path'], context))
        self._wait_for(lambda: self._keyboard_safe(self.find(step['path'], context)),
                       'Text field did not receive keyboard focus')
        # Escape send_keys syntax; literal user text must not become shortcuts.
        escaped = "".join("{" + c + "}" if c in "+^%~(){}" else c for c in text)
        for keys in ("^a", escaped if escaped else "{BACKSPACE}"):
            # Search changes can invalidate SWT's previous UIA provider object.
            # Reobserve the same scoped field; do not replay any earlier input.
            control = self.find(step['path'], context)
            if not self._keyboard_safe(control):
                raise ReviewRequired("Text keyboard focus changed", stage="text entry")
            control.type_keys(keys, set_foreground=False, with_spaces=True, pause=0.01)
        control = self.find(step['path'], context)
        if not self._keyboard_safe(control):
            raise ReviewRequired("Text keyboard focus changed during entry", stage="text entry")
        from .clipboard_table import focus_table
        focus_table(commit,lambda:self._keyboard_safe(commit))
        self._wait_for(lambda:self._keyboard_safe(self.find(step['commit_path'],context)), "Could not leave the text field")
        if not verify_after_blur:
            return  # In-place cell editor is gone; caller verifies the committed grid.
        read_spec = {"path": step["path"], "read": step.get("read", "value")}
        if step.get("transform") == "decimal":
            read_spec["transform"] = "decimal"
        actual = wait_stable(lambda: self._scalar(read_spec, context), timeout=self.timeout)
        matches = amount(actual) == amount(expected) if step.get("transform") == "decimal" else actual == expected
        if not matches:
            raise ReviewRequired("Text was not retained after leaving the field", stage="text entry",
                                 expected=expected, observed=actual)

    def _type_search(self, step, context, value, *, stage):
        """Send SWT search events while keeping keyboard focus in the Edit."""
        if (not isinstance(value, str) or any(ord(c) < 32 for c in value)
                or step.get('commit_path') or step.get('read', 'native_text') != 'native_text'):
            raise ReviewRequired('Search needs plain text without a dialog commit button', stage=stage)
        spec = dict(path=step['path'], read='native_text')

        def field():
            try:
                control = self._find_once(step['path'], context)
            except LookupError as exc:
                # After opening, disappearance is an uncertain transition;
                # never reopen or accept a row in response to it.
                raise ReviewRequired('Search field disappeared during entry', stage=stage) from exc
            if control.element_info.control_type != 'Edit' or not control.is_enabled():
                raise ReviewRequired('Search requires an enabled Edit', stage=stage)
            return control

        control = field()
        if self._scalar(spec, context) == value:
            return
        from .clipboard_table import focus_table
        focus_table(control, lambda: self._keyboard_safe(control))
        escaped = ''.join('{' + c + '}' if c in '+^%~(){}' else c for c in value)
        for keys in ('^a', escaped if escaped else '{BACKSPACE}'):
            control = field()
            if not self._keyboard_safe(control):
                raise ReviewRequired('Search keyboard focus changed', stage=stage)
            control.type_keys(keys, set_foreground=False, with_spaces=True, pause=0.01)

        def retained():
            if not self._keyboard_safe(field()):
                raise ReviewRequired('Search keyboard focus changed during entry', stage=stage)
            return self._scalar(spec, context)

        observed = wait_stable(retained, timeout=self.timeout)
        if observed != value:
            raise ReviewRequired('Search value was not retained', stage=stage, expected=value, observed=observed)

    def _type_address(self, step, context, value):
        from .document_fields import address_lines
        from win32gui import GetWindowLong
        from win32con import GWL_STYLE, ES_MULTILINE
        lines = address_lines(value)
        current = self._scalar({'path':step['path'],'read':'native_text'},context)
        if current.replace('\r\n','\n') == '\n'.join(lines):
            return
        control = self.find(step['path'], context)
        if control.class_name() != 'Edit' or not GetWindowLong(control.handle, GWL_STYLE) & ES_MULTILINE:
            raise ReviewRequired('Address needs the observed multiline Edit', stage='address_entry')
        control.set_focus()
        keys = ['^a']
        for index, line in enumerate(lines):
            if index:
                keys.append('{ENTER}')
            keys.append(''.join('{' + c + '}' if c in '+^%~(){}' else c for c in line))
        for text in keys:
            if not self._keyboard_safe(control):
                raise ReviewRequired('Address focus changed', stage='address_entry')
            control.type_keys(text, set_foreground=False, with_spaces=True, pause=0.01)
        commit = self.find(step['commit_path'], context)
        from .clipboard_table import focus_table
        focus_table(commit,lambda:self._keyboard_safe(commit))
        self._wait_for(lambda:self._keyboard_safe(self.find(step['commit_path'],context)), 'Address did not lose focus')
        actual = self._scalar({'path': step['path'], 'read': 'native_text'}, context)
        if actual.replace('\r\n', '\n') != '\n'.join(lines):
            raise ReviewRequired('Document address was not retained', stage='address_entry', observed=actual)

    def _combo_options(self, control):
        # SWT's UIA .texts() can return the label and Open/Close button names.
        # CB_GETCOUNT/CB_GETLBTEXT read the actual options of this native combo.
        if (control.element_info.control_type != "ComboBox" or not control.handle
                or control.class_name() != "ComboBox"):
            raise ReviewRequired("Options require an observed native ComboBox", stage="dropdown")
        from pywinauto.controls.win32_controls import ComboBoxWrapper
        return ComboBoxWrapper(control.handle).item_texts()

    @staticmethod
    def _vat_code(value):
        match = re.fullmatch(r"([A-Z]{1,3}) \(.+\)", str(value))
        if not match:
            raise ReviewRequired("Unrecognized VAT code option", stage="dropdown", observed=value)
        return match[1]

    def _select_option(self, step, context, value):
        control = self.find(step["path"], context)
        options = self._combo_options(control)
        mode = step.get("option_match", "exact")
        if mode not in ("exact", "vat_code"):
            raise ReviewRequired("Unsupported dropdown matching mode", stage="dropdown")
        matches = [i for i, text in enumerate(options)
                   if key(self._vat_code(text) if mode == "vat_code" else text) == key(value)]
        if len(matches) != 1:
            raise ReviewRequired("Dropdown option missing or ambiguous", stage="dropdown",
                                 expected=value, observed=options)
        expected = options[matches[0]]
        if control.selected_text() != expected:
            control.set_focus()
            # Closed-combo navigation sends normal SWT selection events, without
            # relying on its broken UIA SelectionItem or guessing popup bounds.
            for keys in ["{HOME}", *(["{DOWN}"] * matches[0])]:
                if not self._keyboard_safe(control):
                    raise ReviewRequired("Dropdown focus changed", stage="dropdown")
                control.type_keys(keys, set_foreground=False, pause=0.05)
        actual = wait_stable(control.selected_text, timeout=self.timeout)
        if actual != expected:
            raise ReviewRequired("Dropdown selection was not retained", stage="dropdown",
                                 expected=expected, observed=actual)

    def _navigate_control(self, step, context):
        operation = step.get("operation")
        try:
            if operation == 'select_tree':
                item = self.find(step['path'], context)
                if item.element_info.control_type != 'TreeItem' or not item.is_enabled():
                    raise ReviewRequired('Category requires an enabled TreeItem', stage='UI navigation')
                if not item.is_selected():
                    item.select()
                self._wait_for(lambda: self.find(step['path'], context).is_selected(),
                               'Document category was not selected')
                return
            if operation == "select_tab":
                tab = self.find(step["path"], context)
                if tab.element_info.control_type != "TabItem" or not tab.is_enabled():
                    raise ReviewRequired("select_tab requires an enabled, scoped TabItem", stage="UI navigation")
                if not tab.is_selected():
                    try:
                        tab.select()
                    except Exception:
                        # SWT exposes SelectionItem but its Select method can
                        # return COM "Member not found". Reobserve first, then
                        # click this tab's fresh UIA bounds only if still needed.
                        tab = self.find(step["path"], context)
                        if not tab.is_selected():
                            box = tab.rectangle()
                            if not tab.is_enabled() or box.width() <= 0 or box.height() <= 0:
                                raise ReviewRequired("Tab is not clickable", stage="UI navigation")
                            _click_control(tab)
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

    def _set_date(self, step, context, value):
        control = self.find(step["path"], context)
        commit_path = step.get("commit_path")
        if (control.element_info.control_type != "Edit" or not commit_path
                or commit_path == step["path"]):
            raise ReviewRequired("Date entry needs an Edit and a separate observed focus target", stage="date entry")
        commit = self.find(commit_path, context)
        if not control.is_enabled() or not commit.is_enabled():
            raise ReviewRequired("Date entry or its focus target is disabled", stage="date entry")
        # Whole-value UIA replacement was ignored in live tests even with focus.
        # Use the date widget's segment keyboard handling, not SetValue or paste.
        commit.set_focus()
        self._wait_for(commit.has_keyboard_focus, "Date focus target did not receive focus")
        control.set_focus()
        self._wait_for(control.has_keyboard_focus, "Date field did not receive focus")
        from .date_entry import enter_date
        enter_date(control, day(value), timeout=self.timeout,
                   focus_is_safe=lambda: control.has_keyboard_focus() and _capture_state(self.root())[0])
        # Blur to the known reference control, not Enter (which may invoke a
        # default button). Verify the retained date before any later field write.
        commit = self.find(commit_path, context)
        commit.set_focus()
        self._wait_for(commit.has_keyboard_focus, "Could not leave the date field")
        observed = wait_stable(lambda: self._scalar({"path": step["path"], "transform": "date"}, context),
                               timeout=self.timeout)
        expected = day(value).isoformat()
        if observed != expected:
            raise ReviewRequired("Date was not retained after leaving the field", stage="date entry",
                                 expected=expected, observed=observed)

    def act(self, name, context):
        recipe = self.profile.get("actions", {}).get(name)
        if not recipe:
            raise ReviewRequired("Action not calibrated", stage=name)
        for step in recipe:
            if "when" in step or "unless" in step:
                if "when" in step and "unless" in step:
                    raise ReviewRequired("Action condition is ambiguous", stage=name)
                condition = resolve(step.get("when", step.get("unless")), context)
                if type(condition) is not bool:
                    raise ReviewRequired("Action condition must be boolean", stage=name)
                if condition != ("when" in step):
                    continue
            if step['operation'] == 'edit_item_cell':
                from .item_table import edit_cell
                edit_cell(self, step, context)
                continue
            if step['operation'] == 'open_document_row':
                rows = self.read(step['query'], context)
                number = resolve(step['number'], context)
                matches = [row for row in rows if row['no'] == number]
                if len(matches) != 1:
                    raise ReviewRequired('Saved document number missing or ambiguous', stage=name, expected=number)
                self._select_copied_row({'query': step['query'], 'value': matches[0]}, context)
                continue
            if step["operation"] == "select_copied_row":
                self._select_copied_row(step, context)
                if step.get("wait_query"):
                    self.read(step["wait_query"], context)
                if step.get('wait_absent'):
                    self._wait_absent(step['wait_absent'], context)
                continue
            if step["operation"] in ("select_tab", "scroll_to", 'select_tree'):
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
            elif operation == "focus":
                control.set_focus()
                self._wait_for(control.has_keyboard_focus, "Control did not receive focus")
            elif operation == "dismiss_popup":
                if not step.get("wait_absent"):
                    raise ReviewRequired("Popup dismissal needs a disappearance check", stage=name)
                control.set_focus()
                if not self._keyboard_safe(control):
                    raise ReviewRequired("Popup focus changed before Escape", stage=name)
                control.type_keys("{ESC}", set_foreground=False, pause=0.05)
            elif operation == "select":
                control.select() if value is None else control.select(str(value))
            elif operation == "set":
                if step.get("format") == "date_english":
                    self._set_date(step, context, value)
                else:
                    control.set_edit_text(str(value))
            elif operation == "type_text":
                self._type_text(step, context, value)
            elif operation == 'type_search':
                self._type_search(step, context, value, stage=name)
            elif operation == 'set_search':
                if control.element_info.control_type != 'Edit' or any(ord(c)<32 for c in str(value)):
                    raise ReviewRequired('Search needs a plain-text Edit', stage=name)
                current = self._scalar({'path':step['path'],'read':'native_text'},context)
                if current != str(value):
                    control.set_edit_text(str(value))
                observed = wait_stable(lambda: self._scalar({'path':step['path'],'read':'native_text'},context),
                                       timeout=self.timeout)
                if observed != str(value):
                    raise ReviewRequired('Search value was not retained',stage=name,expected=value,observed=observed)
            elif operation == 'type_address':
                self._type_address(step, context, value)
            elif operation == 'close_clean_editor':
                tab = self.find(step['tab_path'], context)
                if tab.window_text().startswith('*') or not tab.is_selected() or not step.get('wait_absent'):
                    raise ReviewRequired('Editor must be clean and selected before closing', stage=name)
                from .clipboard_table import focus_table
                focus_table(control,lambda:self._keyboard_safe(control))
                if not self._keyboard_safe(control):
                    raise ReviewRequired('Editor focus changed before close', stage=name)
                control.type_keys('^w', set_foreground=False, pause=0.05)
            elif operation == "select_option":
                self._select_option(step, context, value)
            elif operation == "toggle":
                if not isinstance(value, bool):
                    raise ReviewRequired("Checkbox target must be boolean", stage=name)
                if control.get_toggle_state() != int(value):
                    control.toggle()
                self._wait_for(lambda: self.find(step["path"], context).get_toggle_state() == int(value),
                               "Checkbox did not retain its requested state")
            elif operation == "click_bounds":
                # For a UIA-exposed control without Invoke: use its fresh current bounds.
                _click_control(control)
            else:
                raise ReviewRequired("Unsupported UI operation", stage=name, observed=operation)
            if step.get("wait_query"):
                self.read(step["wait_query"], context)
            if step.get("wait_absent"):
                self._wait_absent(step['wait_absent'], context)

    def _wait_absent(self, path, context):
        def absent():
            try:
                self._find_once(path, context)
            except LookupError:
                return True
            return False
        self._wait_for(absent, 'Dialog did not close')

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
