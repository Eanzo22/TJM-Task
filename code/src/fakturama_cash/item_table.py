"""Observed Fakturama item-grid copy format and in-place cell editing."""
import re

from .errors import ReviewRequired
from .normalize import amount


def visible_cell(adapter, path, context, layout, index, column):
    """Scroll the observed editor pane until the grid header and cell are clear.

    SWT reports the entire canvas rectangle even when the outer editor clips
    its last rows. Intersect ancestor rectangles before clicking a cell.
    """
    from .clipboard_table import snapshot_fingerprint
    x = layout['columns'][column]
    y = layout['header_height'] + index * layout['row_height'] + layout['row_height'] // 2
    for _ in range(9):
        table = adapter.find(path, context)
        box = table.rectangle()
        left, top, right, bottom = box.left, box.top, box.right, box.bottom
        scroll = None
        parent = table.parent()
        while parent is not None:
            bounds = parent.rectangle()
            left, top = max(left, bounds.left), max(top, bounds.top)
            right, bottom = min(right, bounds.right), min(bottom, bounds.bottom)
            if scroll is None:
                try:
                    if parent.iface_scroll.CurrentVerticalScrollPercent >= 0:
                        scroll = parent
                except Exception:
                    pass
            parent = parent.parent()
        if (left <= box.left + x < right and top <= box.top
                and box.top + layout['header_height'] <= bottom
                and top <= box.top + y < bottom):
            image = table.capture_as_image()
            header_width = layout.get('header_width', layout['width'])
            header = snapshot_fingerprint(image.crop((0, 0, header_width, layout['header_height'])))
            # The outer editor's scrollbar can disappear after selecting a
            # Debtor, making the canvas wider while all data columns stay put.
            # Extra right-hand space is safe only when the calibrated header
            # remains pixel-identical; never accept a narrower canvas.
            if image.width < layout['width'] or header['sha256'] != layout['header_sha256']:
                raise ReviewRequired('Item grid header changed', stage='item_edit',
                                     expected={'minimum_width': layout['width'],
                                               'header_sha256': layout['header_sha256']},
                                     observed={'width': image.width, 'header_sha256': header['sha256']})
            return table, (x, y)
        # A row beyond the native canvas needs a separately calibrated internal
        # grid scroll mapping; outer scrolling cannot reveal it.
        if scroll is None or y >= box.height():
            break
        direction = 'up' if box.top < top else 'down'
        before = scroll.iface_scroll.CurrentVerticalScrollPercent
        if before == (0 if direction == 'up' else 100):
            break
        scroll.scroll(direction, 'page', count=1)
        if scroll.iface_scroll.CurrentVerticalScrollPercent == before:
            break
    raise ReviewRequired('Item cell is outside the observed viewport', stage='item_edit')


def item_values(row):
    # Observed against Tax-free (0.0%) and a selected 19.0% UI option.
    # The copied model stores tax and discount as fractions, not percentages.
    match = re.match(r'^VAT taxValue: \[([0-9]+(?:\.[0-9]+)?)\] ', row['vat_raw'])
    if not match:
        raise ReviewRequired('Unrecognized copied item VAT', stage='item_read')
    return dict(sku=row['sku'], description=row['name'], quantity=str(amount(row['quantity'])),
                unit_net=str(amount(row['unit_price'])), vat_percent=str(amount(match[1]) * 100),
                discount_percent=str(-amount(row['discount_raw']) * 100),
                source_net=str(amount(row['line_price'])))


def edit_cell(adapter, step, context):
    from .clipboard_table import copy_table, parse_table
    from .ui import resolve, _click_control
    spec = adapter.profile['queries'][step['query']]
    config = spec['clipboard_rows']
    index = resolve(step['index'], context)
    expected_sku = resolve(step['sku'], context)
    column = step['column']
    layout = step['layout']
    if type(index) is not int or index < 0 or column not in layout['columns']:
        raise ReviewRequired('Invalid item cell mapping', stage='item_edit')
    table = adapter.find(spec['path'], context)
    rows = parse_table(copy_table(table, is_safe=lambda: adapter._keyboard_safe(table), timeout=adapter.timeout),
                       config['columns'], format=config.get('format', 'raw_tsv'))
    if index >= len(rows) or rows[index]['sku'] != expected_sku:
        raise ReviewRequired('Item row does not match the intended product', stage='item_edit')
    value = resolve(step['value'], context)
    fields = {'quantity': 'quantity', 'unit_price': 'unit_net', 'discount': 'discount_percent',
              'vat': 'vat_percent', 'name': 'description'}
    current = item_values(rows[index])[fields[column]]
    # Preserve already correct cells, including the product's tax definition
    # when several definitions share the source percentage.
    if (current == str(value) if column == 'name' else amount(current) == amount(value)):
        return
    table, point = visible_cell(adapter, spec['path'], context, layout, index, column)
    _click_control(table, relative=point, double=True)
    editor_path = spec['path'] + [{'control_type': 'Edit'}]
    editor = adapter.find(editor_path, context)
    if column == 'vat':
        # SWT CCombo uses a text Edit and an accessible popup List.
        editor.set_focus()
        if not adapter._keyboard_safe(editor):
            raise ReviewRequired('VAT editor focus changed', stage='item_edit')
        editor.type_keys('%{DOWN}', set_foreground=False, pause=0.05)
        options = adapter.root().descendants(control_type='ListItem')
        matches = []
        for option in options:
            rate = re.fullmatch(r'.+ \(([0-9]+(?:\.[0-9]+)?)%\)', option.window_text())
            if option.is_visible() and rate and amount(rate[1]) == amount(value):
                matches.append(option)
        if len(matches) > 1:
            canonical = f'VAT {amount(value).normalize():f}%'
            matches = [option for option in matches if option.window_text().startswith(canonical + ' (')]
        if len(matches) != 1:
            raise ReviewRequired('Item VAT rate missing or ambiguous', stage='item_edit')
        _click_control(matches[0])
        adapter.find(step['commit_path'], context).set_focus()
    else:
        write = dict(path=editor_path, commit_path=step['commit_path'], read='native_text')
        if column in ('quantity', 'unit_price', 'discount'):
            write.update(transform='decimal', decimal_separator=',' if column == 'unit_price' else '.')
        # Cell editors are destroyed on blur: verify the committed row below.
        adapter._type_text(write, context, value, verify_after_blur=False)
    fresh = adapter.find(spec['path'], context)
    observed = parse_table(copy_table(fresh, is_safe=lambda: adapter._keyboard_safe(fresh), timeout=adapter.timeout),
                           config['columns'], format=config.get('format', 'raw_tsv'))
    if index >= len(observed) or observed[index]['sku'] != expected_sku:
        raise ReviewRequired('Item row changed during editing', stage='item_edit')
    actual = item_values(observed[index])[fields[column]]
    if (actual != str(value) if column == 'name' else amount(actual) != amount(value)):
        raise ReviewRequired('Item cell was not retained', stage='item_edit', expected=value, observed=actual)
