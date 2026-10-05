"""Guided device-specific geometry calibration, without business writes."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

from .clipboard_table import focus_table, snapshot_fingerprint, validate_copy_config
from .errors import ReviewRequired
from .state import write_json
from .ui import UIAAdapter
from .workflow import ACTIONS, QUERIES


TABLES = (
    ('documents_orders', 'Documents: Orders', 'Open Documents and select Orders.'),
    ('documents_invoices', 'Documents: Invoices', 'Select Invoices in Documents.'),
    ('vat_results', 'VATs', 'Open the VATs list.'),
    ('payment_results', 'Terms of payment', 'Open the terms of payment list.'),
    ('product_results', 'Product selector', 'Open a temporary New Order and its Select a product dialog.'),
    ('debtor_results', 'Debtor selector', 'Cancel the product dialog and open Select the address on that Order.'),
    ('items_raw', 'Order items', 'Cancel the address dialog. Show a temporary New Order in Net/With VAT mode.'),
)


def capture_table(adapter, spec, context):
    """Capture a stationary foreground grid in the bound Fakturama process."""
    from pywinauto.controls.hwndwrapper import HwndWrapper
    from win32gui import GetAncestor
    from .ui import _activate_capture_window, _capture_state, _wait_capture_ready

    table = adapter.find(spec['path'], context)
    parent = table
    while parent is not None and not parent.handle:
        parent = parent.parent()
    if parent is None:
        raise ReviewRequired('Table has no native capture window', stage='calibration')
    window = HwndWrapper(GetAncestor(parent.handle, 2))
    if window.process_id() != adapter.root().process_id():
        raise ReviewRequired('Calibration table belongs to another process', stage='calibration')
    _activate_capture_window(window)
    bounds = _wait_capture_ready(window, adapter.timeout)
    focus_table(table, lambda: adapter._keyboard_safe(table))
    if not adapter._keyboard_safe(table):
        raise ReviewRequired('Table did not receive safe focus', stage='calibration')
    table.type_keys('^{HOME}', set_foreground=False, pause=0.05)
    identity = tuple(table.element_info.runtime_id)
    box = table.rectangle()
    rectangle = (box.left, box.top, box.right, box.bottom)
    if not (bounds[0] <= box.left < box.right <= bounds[2]
            and bounds[1] <= box.top < box.bottom <= bounds[3]):
        raise ReviewRequired('Table is clipped; expose its full area before calibration', stage='calibration')
    ancestor = table.parent()
    while ancestor is not None:
        if ancestor.is_visible():
            limit = ancestor.rectangle()
            if limit.width() > 0 and limit.height() > 0 and not (
                    limit.left <= box.left and box.right <= limit.right
                    and limit.top <= box.top and box.bottom <= limit.bottom):
                raise ReviewRequired('Table is clipped by its editor; expose the full table', stage='calibration')
        ancestor = ancestor.parent()

    def capture():
        if not adapter._keyboard_safe(table) or _capture_state(window) != (True, bounds):
            raise ReviewRequired('Table focus or window bounds changed', stage='calibration')
        image = table.capture_as_image()
        fresh = adapter.find(spec['path'], context)
        if (tuple(fresh.element_info.runtime_id) != identity or fresh.rectangle() != box
                or _capture_state(window) != (True, bounds)
                or image is None or image.size != (box.width(), box.height())):
            raise ReviewRequired('Table changed during capture', stage='calibration')
        return image

    first = capture()
    time.sleep(0.2)
    second = capture()
    if snapshot_fingerprint(first) != snapshot_fingerprint(second):
        raise ReviewRequired('Table image is not stable; keep it unobstructed', stage='calibration')
    return second, {'rectangle': list(rectangle), 'capture_method': 'foreground_screen_region',
                    'foreground_verified_before_and_after': True}


def measurement(empty_image, populated_image, marks, *, items=False):
    """Reject incompatible captures and build measurements from reviewed pixels."""
    if empty_image.size != populated_image.size:
        raise ReviewRequired('Table bounds differ between empty and populated captures', stage='calibration',
                             expected=list(empty_image.size), observed=list(populated_image.size))
    if marks.get('columns_confirmed') is not True:
        raise ReviewRequired('Table columns were not reviewed', stage='calibration')
    for key in ('header_height', 'row_height', 'first_row_bottom', 'expected_count'):
        if type(marks.get(key)) is not int or marks[key] < 1:
            raise ReviewRequired('Invalid row measurement', stage='calibration', observed=key)
    header, row = marks['header_height'], marks['row_height']
    if header + row != marks['first_row_bottom'] or header + row > populated_image.height:
        raise ReviewRequired('First-row bounds are invalid', stage='calibration')
    header_width = marks.get('header_width', populated_image.width) if items else populated_image.width
    if type(header_width) is not int or not 0 < header_width <= populated_image.width:
        raise ReviewRequired('Invalid header width', stage='calibration')
    fingerprint = snapshot_fingerprint(populated_image.crop((0, 0, header_width, header)))['sha256']
    if items:
        columns = {k: marks.get(k) for k in ('quantity', 'name', 'vat', 'unit_price', 'discount')}
        if (any(type(x) is not int or not 0 < x < header_width for x in columns.values())
                or list(columns.values()) != sorted(set(columns.values()))):
            raise ReviewRequired('Item column positions are invalid or out of order', stage='calibration')
        layout = {'width': populated_image.width, 'header_height': header, 'row_height': row,
                  'header_width': header_width, 'header_sha256': fingerprint, 'columns': columns}
        snapshot = snapshot_fingerprint(empty_image.crop((0, 0, empty_image.width, header + row)))
        return {'empty_snapshot': snapshot, 'empty_crop': True}, layout
    x = marks.get('column_x')
    if type(x) is not int or not 0 < x < populated_image.width:
        raise ReviewRequired('Invalid row click position', stage='calibration')
    hashes = [fingerprint, snapshot_fingerprint(empty_image.crop((0, 0, empty_image.width, header)))['sha256']]
    return {'empty_snapshot': snapshot_fingerprint(empty_image), 'row_geometry': {
        'width': populated_image.width, 'header_height': header, 'row_height': row,
        'column_x': x, 'header_sha256': list(dict.fromkeys(hashes))}}, None


def apply_measurement(profile, query, updates, layout=None):
    """Update nested Order aliases as well as top-level query mappings."""
    queries = profile['queries']
    source = queries[query]['clipboard_rows']
    # The item query is embedded in line/order/body observations. Match semantic
    # columns; Invoice shares that copy format but intentionally has no empty test.
    def walk(value):
        if isinstance(value, dict):
            config = value.get('clipboard_rows')
            if config is not None and (value is queries[query] or
                    (query == 'items_raw' and config.get('columns') == source['columns']
                     and 'empty_snapshot' in config)):
                config.update(deepcopy(updates))
                validate_copy_config(config)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(queries)
    if query == 'documents_invoices':
        queries['documents_raw']['clipboard_rows'].update(deepcopy(updates))
    if layout is not None:
        for steps in profile['actions'].values():
            for step in steps:
                if step.get('operation') == 'edit_item_cell' and step.get('query') == query:
                    step['layout'] = deepcopy(layout)


def calibrate(profile_path, output_path, directory, *, order_editor='New Order',
              prompt=input, review=None, capture=capture_table, adapter_factory=UIAAdapter, progress=None):
    from .calibration_view import review_image
    review = review or review_image
    progress = progress or (lambda message: None)
    profile_path, output_path, directory = Path(profile_path), Path(output_path), Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    original = profile_path.read_bytes()
    original_output = output_path.read_bytes() if output_path.exists() else None
    profile = json.loads(original)
    profile['calibrated'] = True  # Check mapping completeness without connecting.
    adapter_factory(profile, desktop=object()).preflight(ACTIONS, QUERIES, connect=False)
    profile['calibrated'] = False
    adapter = adapter_factory(profile)
    adapter.prepare_window()
    context = {'order_editor': order_editor}
    completed = []
    write_json(directory / 'source-profile.json', json.loads(original))
    progress('Calibration: no Save, record creation or row activation is performed by this command')
    for query, label, navigation in TABLES:
        spec = profile['queries'][query]
        progress(f'Calibrating {label}')
        items = query == 'items_raw'
        empty_instruction = ('Keep the temporary Order item grid empty.' if items else
                             'Use its Search box to produce ZERO results (do not delete records).')
        prompt(f'\n{label}: {navigation}\n{empty_instruction}\n'
               'Keep MAIN Fakturama maximized; leave selectors at their normal size. '
               'Keep the table unobstructed. Return to CMD and press Enter to capture: ')
        empty_image, empty_meta = capture(adapter, spec, context)
        empty_image.save(directory / (query + '-empty.png'))
        if review(empty_image, label + ': confirm EMPTY results', empty=True).get('empty_confirmed') is not True:
            raise ReviewRequired('Empty state was not confirmed', stage='calibration')
        prompt(('\nAdd one existing test product to this UNSAVED Order; do not save it.' if items else
                '\nClear the Search filter and show at least one existing test row. '
                'Confirm the total number of results, including off-screen rows.') +
               '\nLeave the same table at the same size, return to CMD and press Enter: ')
        populated_image, populated_meta = capture(adapter, spec, context)
        populated_image.save(directory / (query + '-populated.png'))
        marks = review(populated_image, label + ': mark row boundaries and columns', items=items)
        updates, layout = measurement(empty_image, populated_image, marks, items=items)
        # The review window temporarily owns foreground focus. Reacquire the
        # grid and verify that the reviewed results still exist before copying.
        current_image, _ = capture(adapter, spec, context)
        if snapshot_fingerprint(current_image) != snapshot_fingerprint(populated_image):
            raise ReviewRequired('Table changed while its capture was being reviewed', stage='calibration')
        apply_measurement(profile, query, updates, layout)
        # Copy known nonempty rows only, through the same runtime table reader.
        # The count is checked against the operator's complete result count.
        rows = adapter._read_copied_rows(spec, context, allow_unverified=False)
        if len(rows) != marks['expected_count']:
            raise ReviewRequired('Copied rows do not match the reviewed total; copy scope is not calibrated',
                                 stage='calibration', expected=marks['expected_count'], observed=len(rows))
        if not rows:
            raise ReviewRequired('A populated table is required for calibration', stage='calibration')
        write_json(directory / (query + '-measurement.json'), {
            'query': query, 'empty_capture': empty_meta, 'populated_capture': populated_meta,
            'empty_confirmed': True, 'marks': marks, 'copied_row_count': len(rows),
            'clipboard_rows': updates, 'item_layout': layout})
        completed.append(query)
        write_json(directory / 'draft-profile.json', profile)
    profile['calibration'] = {
        'kind': 'guided_local_table_geometry', 'completed_tables': completed,
        'device': platform.node(), 'created_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': hashlib.sha256(original).hexdigest(),
        'evidence': str(directory), 'business_writes': False,
        'scope': 'Existing English UI selectors; table geometry and copy counts, not an end-to-end transaction'}
    profile['calibrated'] = True
    adapter_factory(profile, desktop=object()).preflight(ACTIONS, QUERIES, connect=False)
    # Preserve an existing output, and detect external changes before replacement.
    if profile_path.read_bytes() != original:
        raise ReviewRequired('Source profile changed during calibration', stage='calibration')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if (output_path.read_bytes() if output_path.exists() else None) != original_output:
        raise ReviewRequired('Output profile changed during calibration', stage='calibration')
    if original_output is not None:
        (directory / 'previous-output-profile.json').write_bytes(original_output)
    write_json(output_path, profile)
    return {'status': 'calibrated_local_profile', 'profile': str(output_path), 'tables': completed,
            'evidence': str(directory), 'business_writes': False}
