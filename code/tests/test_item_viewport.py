from types import SimpleNamespace

import pytest
from PIL import Image

from fakturama_cash.clipboard_table import snapshot_fingerprint
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.item_table import visible_cell


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom
    def height(self):
        return self.bottom - self.top


def scene():
    offset = [0]
    image = Image.new('RGB', (200, 124), 'white')
    parent = SimpleNamespace(rectangle=lambda: Rect(0, 0, 220, 110), parent=lambda: None,
                             iface_scroll=SimpleNamespace(CurrentVerticalScrollPercent=0))
    def scroll(direction, unit, count):
        assert (direction, unit, count) == ('down', 'page', 1)
        offset[0] = 25
        parent.iface_scroll.CurrentVerticalScrollPercent = 100
    parent.scroll = scroll
    table = SimpleNamespace(rectangle=lambda: Rect(0, 10-offset[0], 200, 134-offset[0]),
                            parent=lambda: parent, capture_as_image=lambda: image)
    # Header must remain inside the clipped parent after scrolling. In this
    # example the pane top follows the observed scroll viewport.
    parent.rectangle = lambda: Rect(0, -20, 220, 110)
    layout = dict(width=200, header_height=25, row_height=25, columns={'name': 90},
                  header_sha256=snapshot_fingerprint(image.crop((0,0,200,25)))['sha256'])
    adapter = SimpleNamespace(find=lambda *args: table)
    return adapter, table, parent, layout


def test_clipped_fourth_row_scrolls_before_click_position_is_returned():
    adapter, table, parent, layout = scene()
    result, point = visible_cell(adapter, 'grid', {}, layout, 3, 'name')
    assert result is table and point == (90,112)
    assert parent.iface_scroll.CurrentVerticalScrollPercent == 100
    assert table.rectangle().top + point[1] < parent.rectangle().bottom


def test_native_canvas_limit_is_not_bypassed_by_scrolling_outer_editor():
    adapter, _, parent, layout = scene()
    with pytest.raises(ReviewRequired, match='outside'):
        visible_cell(adapter, 'grid', {}, layout, 4, 'name')
    assert parent.iface_scroll.CurrentVerticalScrollPercent == 0


def test_header_guard_ignores_only_calibrated_unused_scrollbar_tail():
    adapter, table, _, layout=scene()
    image=table.capture_as_image()
    layout['header_width']=150
    layout['header_sha256']=snapshot_fingerprint(image.crop((0,0,150,25)))['sha256']
    image.paste('gray',(150,0,200,25))
    visible_cell(adapter,'grid',{},layout,0,'name')
    image.putpixel((20,5),(0,0,0))
    with pytest.raises(ReviewRequired,match='header changed'):
        visible_cell(adapter,'grid',{},layout,0,'name')
