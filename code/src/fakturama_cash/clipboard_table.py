"""Read custom grids through their UI copy command, without OCR or database access."""
import csv
import hashlib
import io
import json
import re
import time

from .errors import ReviewRequired


def header_matches(image, expected):
    fingerprints = expected if isinstance(expected, list) else [expected]
    return snapshot_fingerprint(image)['sha256'] in fingerprints


def validate_copy_config(config, *, allow_unverified=False):
    if (not isinstance(config, dict) or not set(config) <= {"columns", "headers", "copy_scope", "keyboard_selection", "empty_snapshot", "row_geometry", "format", "row_walk", 'empty_crop'}
            or config.get("copy_scope") not in ({"all_rows", "unverified"} if allow_unverified else {"all_rows"})):
        raise ReviewRequired("Grid copy must be calibrated to include all result rows", stage="table_read")
    if 'empty_crop' in config and (config['empty_crop'] is not True or 'empty_snapshot' not in config):
        raise ReviewRequired('Empty crop needs a calibrated snapshot', stage='table_read')
    columns = config.get("columns")
    if (not isinstance(columns, list) or not columns
            or any(not isinstance(c, str) or not c or c.startswith("_") for c in columns)
            or len(set(columns)) != len(columns)):
        raise ReviewRequired("Table columns must be unique semantic names", stage="table_read")
    if "row_walk" in config:
        walk = config['row_walk']
        if (not isinstance(walk, dict) or set(walk) != {'identity', 'max_rows'}
                or walk['identity'] not in columns or type(walk['max_rows']) is not int
                or not 1 <= walk['max_rows'] <= 1000):
            raise ReviewRequired("Invalid bounded row walk", stage="table_read")
    if "headers" in config and (not isinstance(config["headers"], list)
                               or len(config["headers"]) != len(columns)
                               or not all(isinstance(h, str) for h in config["headers"])):
        raise ReviewRequired("Invalid copied table header configuration", stage="table_read")
    if "keyboard_selection" in config and config["keyboard_selection"] not in ("ctrl_home_down_enter", "ctrl_home_down_double_click"):
        raise ReviewRequired("Unsupported table keyboard selection", stage="table_read")
    if config.get("format", "quoted_tsv") not in ("quoted_tsv", "raw_tsv"):
        raise ReviewRequired("Unsupported table copy format", stage="table_read")
    if config.get("keyboard_selection") == "ctrl_home_down_double_click" or 'row_walk' in config:
        geometry = config.get("row_geometry", {})
        if (not isinstance(geometry, dict) or set(geometry) != {"header_height", "row_height", "column_x", "width", "header_sha256"}
                or any(type(geometry.get(k)) is not int or geometry[k] < 1
                       for k in ("header_height", "row_height", "column_x", "width"))
                or geometry["column_x"] >= geometry["width"]
                or not valid_header_hashes(geometry.get('header_sha256'))):
            raise ReviewRequired("Double-click selection requires calibrated row geometry", stage="table_select")
    if "empty_snapshot" in config:
        snapshot = config["empty_snapshot"]
        if (not isinstance(snapshot, dict) or set(snapshot) != {"width", "height", "sha256"}
                or any(type(snapshot.get(k)) is not int or snapshot[k] < 1 for k in ("width", "height"))
                or not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("sha256", "")))):
            raise ReviewRequired("Invalid calibrated empty-table snapshot", stage="table_read")


def valid_header_hashes(value):
    values = value if isinstance(value, list) else [value]
    return bool(values) and all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{64}',v) for v in values)


def snapshot_fingerprint(image):
    """Exact pixels of a visually verified empty grid, including its headings."""
    image = image.convert("RGB")
    return {"width": image.width, "height": image.height,
            "sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def parse_table(text, columns, *, headers=None, expected_count=None, empty_confirmed=False, format="quoted_tsv"):
    """Parse tab-separated UI output, preserving order, blanks and duplicates."""
    validate_copy_config({"columns": columns, "copy_scope": "all_rows", "format": format})
    if expected_count is not None and (type(expected_count) is not int or expected_count < 0):
        raise ReviewRequired("Invalid table result count", stage="table_read")
    if not isinstance(text, str) or "\x00" in text:
        raise ReviewRequired("Table copy did not return plain text", stage="table_read")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True,
                               quoting=csv.QUOTE_NONE if format == "raw_tsv" else csv.QUOTE_MINIMAL))
    except csv.Error as exc:
        raise ReviewRequired("Malformed copied table", stage="table_read") from exc
    if headers is not None:
        if not isinstance(headers, list) or len(headers) != len(columns) or not rows or rows.pop(0) != headers:
            raise ReviewRequired("Copied table headers do not match calibration", stage="table_read")
    # An empty clipboard (or header alone) is not proof of an empty result set.
    if not rows:
        if not empty_confirmed or expected_count not in (None, 0):
            raise ReviewRequired("Cannot distinguish empty from failed table copy", stage="table_read")
        return []
    if any(len(row) != len(columns) or not any(cell.strip() for cell in row) for row in rows):
        raise ReviewRequired("Copied table has missing columns or blank rows", stage="table_read")
    if any("…" in cell or "..." in cell for row in rows for cell in row):
        raise ReviewRequired("Copied table contains truncated text", stage="table_read")
    if expected_count is not None and len(rows) != expected_count:
        raise ReviewRequired("Copied row count does not match the result count", stage="table_read",
                             expected=expected_count, observed=len(rows))
    return [dict(zip(columns, row)) for row in rows]


def table_fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def focus_table(control, is_safe):
    control.set_focus()
    if not is_safe() and getattr(control,'handle',None):
        from win32gui import GetAncestor, GetForegroundWindow, IsWindowEnabled
        from pywinauto.controls.hwndwrapper import HwndWrapper
        root = GetAncestor(control.handle,2)
        if (GetAncestor(GetForegroundWindow(),2)==root and IsWindowEnabled(root)
                and control.is_enabled()):
            # SWT's SetFocus can leave focus in the previous editor. Set native
            # keyboard focus only inside the already foreground, enabled window.
            HwndWrapper(control.handle).set_keyboard_focus()


def walk_table(control, config, *, is_safe, timeout):
    """Read single-selection grids with calibrated Home/Down/End navigation.

    A repeated row is a boundary only when Ctrl+End confirms the same row.
    Identity collisions, focus loss and the row limit stop the read.
    """
    def move(keys):
        if not is_safe():
            raise ReviewRequired("Table focus changed during row walk", stage="table_read")
        control.type_keys(keys, set_foreground=False, pause=0.05)

    def current():
        text = copy_table(control, is_safe=is_safe, timeout=timeout, select_all=False)
        return parse_table(text, config['columns'], expected_count=1,
                           format=config.get('format', 'quoted_tsv'))[0]

    focus_table(control,is_safe)
    move('^{HOME}')
    rows, seen = [], set()
    identity = config['row_walk']['identity']
    for _ in range(config['row_walk']['max_rows'] + 1):
        row = current()
        if rows and row == rows[-1]:
            move('^{END}')
            if current() != row:
                raise ReviewRequired("Row navigation stopped before the last result", stage="table_read")
            return rows
        if not row[identity].strip() or row[identity] in seen:
            raise ReviewRequired("Row identity missing or repeated", stage="table_read")
        if len(rows) == config['row_walk']['max_rows']:
            break
        rows.append(row)
        seen.add(row[identity])
        move('{DOWN}')
    raise ReviewRequired("Table exceeds the bounded row limit", stage="table_read")


class WindowsClipboard:
    """Do not clear the clipboard: its sequence number distinguishes new copies."""
    def sequence(self):
        import win32clipboard
        return win32clipboard.GetClipboardSequenceNumber()

    def owner_process(self):
        import win32clipboard
        from win32process import GetWindowThreadProcessId
        owner = win32clipboard.GetClipboardOwner()
        return GetWindowThreadProcessId(owner)[1] if owner else None

    def read(self):
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                raise ReviewRequired("Grid did not copy Unicode text", stage="table_read")
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()


def copy_table(control, *, is_safe, timeout, clipboard=None, select_all=True):
    """Select/copy once. Only clipboard observation is retried, never UI input."""
    clipboard = clipboard if clipboard is not None else WindowsClipboard()
    focus_table(control,is_safe)
    if not is_safe():
        raise ReviewRequired("Table keyboard focus or foreground changed", stage="table_read")
    if select_all:
        control.type_keys("^a", set_foreground=False, pause=0.05)
    if not is_safe():
        raise ReviewRequired("Table keyboard focus changed before copy", stage="table_read")
    before = clipboard.sequence()
    control.type_keys("^c", set_foreground=False, pause=0.05)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_safe():
            raise ReviewRequired("Table keyboard focus changed during copy", stage="table_read")
        sequence = clipboard.sequence()
        if sequence != before:
            if clipboard.owner_process() != control.process_id():
                raise ReviewRequired("Clipboard was updated by another application", stage="table_read")
            try:
                text = clipboard.read()
            except OSError:
                time.sleep(0.05)  # Clipboard can briefly be held by the application.
                continue
            if clipboard.sequence() != sequence:
                raise ReviewRequired("Clipboard changed while reading the table", stage="table_read")
            return text
        time.sleep(0.05)
    raise ReviewRequired("Grid copy did not update the clipboard", stage="table_read",
                         next_action="Verify Ctrl+A/Ctrl+C support in this grid; do not treat stale clipboard text as rows.")
