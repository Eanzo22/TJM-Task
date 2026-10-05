from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

from fakturama_cash.calibration import TABLES, apply_measurement, calibrate, measurement
from fakturama_cash.clipboard_table import snapshot_fingerprint
from fakturama_cash.errors import ReviewRequired


def built_profile():
    code = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location('profile_builder', code / 'scripts/build_live_profile.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    # The builder intentionally resolves component files from code/.
    return builder.build()


def images():
    empty = Image.new('RGB', (900, 200), 'white')
    ImageDraw.Draw(empty).rectangle((0, 0, 899, 29), fill='grey')
    populated = empty.copy()
    ImageDraw.Draw(populated).rectangle((0, 30, 899, 59), fill='blue')
    return empty, populated


def marks(*, items=False):
    result = {'header_height': 30, 'row_height': 30, 'first_row_bottom': 60,
              'expected_count': 3, 'columns_confirmed': True, 'column_x': 80}
    if items:
        result.update(header_width=780, quantity=90, name=250, vat=400, unit_price=530, discount=650)
    return result


def test_measurements_use_new_device_pixels():
    empty, populated = images()
    updates, layout = measurement(empty, populated, marks())
    assert layout is None
    assert updates['empty_snapshot'] == snapshot_fingerprint(empty)
    assert updates['row_geometry']['width'] == 900
    assert updates['row_geometry']['header_height'] == 30
    assert updates['row_geometry']['row_height'] == 30
    assert snapshot_fingerprint(populated.crop((0, 0, 900, 30)))['sha256'] in updates['row_geometry']['header_sha256']


@pytest.mark.parametrize('change', [
    {'columns_confirmed': False}, {'expected_count': 0}, {'header_height': True},
    {'first_row_bottom': 61}, {'column_x': 901},
])
def test_invalid_measurements_stop(change):
    empty, populated = images()
    with pytest.raises(ReviewRequired):
        measurement(empty, populated, {**marks(), **change})


def test_resizing_between_captures_stops():
    empty, populated = images()
    with pytest.raises(ReviewRequired, match='bounds differ'):
        measurement(empty, populated.resize((899, 200)), marks())


@pytest.mark.parametrize('change', [{'header_width': 950}, {'quantity': 0}, {'vat': 250}])
def test_invalid_item_column_layout_stops(change):
    empty, populated = images()
    with pytest.raises(ReviewRequired):
        measurement(empty, populated, {**marks(items=True), **change}, items=True)


def test_nested_item_queries_and_all_edit_actions_are_updated(monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    profile = built_profile()
    invoice_before = deepcopy(profile['queries']['invoice_items']['clipboard_rows'])
    updates, layout = measurement(*images(), marks(items=True), items=True)
    apply_measurement(profile, 'items_raw', updates, layout)
    for query in ('items_raw', 'line', 'order_items'):
        assert profile['queries'][query]['clipboard_rows']['empty_snapshot']['height'] == 60
    assert profile['queries']['order_body']['fields']['items']['clipboard_rows']['empty_snapshot']['width'] == 900
    assert profile['queries']['invoice_items']['clipboard_rows'] == invoice_before
    assert profile['queries']['invoice_body']['fields']['items']['clipboard_rows'] == invoice_before
    assert all(step['layout'] == layout for step in profile['actions']['fill_line'])


def test_documents_categories_keep_separate_measurements(monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    profile = built_profile()
    orders, _ = measurement(*images(), marks())
    invoices = deepcopy(orders)
    invoices['empty_snapshot']['sha256'] = 'b' * 64
    apply_measurement(profile, 'documents_orders', orders)
    apply_measurement(profile, 'documents_invoices', invoices)
    assert profile['queries']['documents_orders']['clipboard_rows']['empty_snapshot'] == orders['empty_snapshot']
    assert profile['queries']['documents_invoices']['clipboard_rows']['empty_snapshot'] == invoices['empty_snapshot']
    assert profile['queries']['documents_raw']['clipboard_rows']['empty_snapshot'] == invoices['empty_snapshot']


def calibration_fakes(monkeypatch, tmp_path, *, fail=None):
    from fakturama_cash.ui import UIAAdapter
    monkeypatch.chdir(Path(__file__).parents[1])
    source, output = tmp_path / 'source.json', tmp_path / 'local.json'
    source.write_text(json.dumps(built_profile()))
    output.write_text('{"existing":"preserved"}')
    empty, populated = images()
    captures, events = {}, []

    class Adapter(UIAAdapter):
        def __init__(self, profile, desktop=None):
            self.profile = profile

        def preflight(self, *args, **kwargs):
            # Use the real completeness checker without a Windows desktop.
            UIAAdapter(self.profile, desktop=object()).preflight(*args, **kwargs)

        def prepare_window(self):
            events.append('prepare')

        def act(self, *args):
            pytest.fail('Calibration must not invoke business actions')

    def read_rows(self, spec, context, **kwargs):
        assert spec['clipboard_rows']['empty_snapshot']['width'] == 900
        events.append('copy')
        return [{}] * (2 if fail == 'row_count' else 3)

    # Patch an existing concrete adapter method, so a name/signature mismatch
    # cannot be hidden by an invented method on the fake adapter.
    monkeypatch.setattr(UIAAdapter, '_read_copied_rows', read_rows)

    def capture(adapter, spec, context):
        key = id(spec)
        captures[key] = captures.get(key, 0) + 1
        sequence = captures[key]
        image = empty if sequence == 1 else populated
        if fail == 'changed_capture' and sequence == 3:
            image = Image.new('RGB', populated.size, 'red')
        if fail == 'source_changed' and len(captures) == len(TABLES):
            source.write_text('{}')
        if fail == 'output_changed' and len(captures) == len(TABLES):
            output.write_text('{"external":"change"}')
        return image.copy(), {'rectangle': [0, 0, 900, 200]}

    def review(image, title, *, empty=False, items=False):
        if fail == 'cancelled':
            raise ReviewRequired('Cancelled', stage='calibration')
        if empty:
            return {'empty_confirmed': fail != 'not_empty'}
        return marks(items=items)

    return source, output, dict(adapter_factory=Adapter, capture=capture, review=review,
                               prompt=lambda text: events.append('prompt')), events


def test_guided_full_calibration_writes_separate_profile_and_evidence(monkeypatch, tmp_path):
    source, output, kwargs, events = calibration_fakes(monkeypatch, tmp_path)
    original = source.read_bytes()
    result = calibrate(source, output, tmp_path / 'evidence', **kwargs)
    profile = json.loads(output.read_text())
    assert source.read_bytes() == original
    assert result['status'] == 'calibrated_local_profile'
    assert result['business_writes'] is False
    assert result['tables'] == [query for query, *_ in TABLES]
    assert profile['calibrated'] is True
    assert profile['calibration']['completed_tables'] == result['tables']
    assert events.count('copy') == len(TABLES)
    assert json.loads((tmp_path / 'evidence/previous-output-profile.json').read_text()) == {'existing': 'preserved'}
    assert len(list((tmp_path / 'evidence').glob('*-measurement.json'))) == len(TABLES)
    assert json.loads((tmp_path / 'evidence/draft-profile.json').read_text())['calibrated'] is False


@pytest.mark.parametrize('fail', ['row_count', 'changed_capture', 'cancelled', 'not_empty', 'source_changed', 'output_changed'])
def test_incomplete_or_changed_calibration_never_replaces_output(monkeypatch, tmp_path, fail):
    source, output, kwargs, events = calibration_fakes(monkeypatch, tmp_path, fail=fail)
    with pytest.raises(ReviewRequired):
        calibrate(source, output, tmp_path / 'evidence', **kwargs)
    assert json.loads(output.read_text()) == ({'external': 'change'} if fail == 'output_changed' else {'existing': 'preserved'})
    if fail in ('changed_capture', 'not_empty', 'cancelled'):
        assert 'copy' not in events


@pytest.mark.parametrize('fails', [False, True])
def test_calibrate_cli_reports_result_or_review_with_sound(monkeypatch, tmp_path, capsys, fails):
    from fakturama_cash import calibration, cli
    events = []

    def fake_calibrate(source, output, directory, **kwargs):
        directory.mkdir(parents=True)
        if fails:
            raise ReviewRequired('Invalid measurement', stage='calibration')
        return {'status': 'calibrated_local_profile', 'profile': str(output), 'business_writes': False}

    monkeypatch.setattr(calibration, 'calibrate', fake_calibrate)
    monkeypatch.setattr(cli, 'capture_finished', lambda *, success: events.append(success))
    assert cli.main(['calibrate', '--out', str(tmp_path)]) == (2 if fails else 0)
    output = capsys.readouterr()
    result = json.loads(output.err.splitlines()[-1] if fails else output.out)
    assert result['status'] == ('review_required' if fails else 'calibrated_local_profile')
    assert events == [not fails]
    if fails:
        assert Path(result['evidence']).is_file()


@pytest.mark.parametrize('failure', [None, 'foreign_process', 'clipped', 'focus_lost', 'wrong_size', 'unstable'])
def test_windows_capture_guards_without_desktop_input(monkeypatch, failure):
    from fakturama_cash import calibration, ui

    class Rectangle:
        left, top, right, bottom = 100, 100, 300, 220

        def width(self):
            return self.right - self.left

        def height(self):
            return self.bottom - self.top

    box = Rectangle()
    window = SimpleNamespace(handle=42, process_id=lambda: 99 if failure == 'foreign_process' else 7)
    events = []

    class Table:
        handle = 43
        element_info = SimpleNamespace(runtime_id=(1, 2))

        def rectangle(self):
            return box

        def parent(self):
            return None

        def type_keys(self, keys, **kwargs):
            events.append(keys)

        def set_focus(self):
            events.append('focus')

        def capture_as_image(self):
            events.append('capture')
            size = (199, 120) if failure == 'wrong_size' else (200, 120)
            color = 'blue' if failure == 'unstable' and events.count('capture') == 2 else 'white'
            return Image.new('RGB', size, color)

    table = Table()
    adapter = SimpleNamespace(find=lambda *args: table, root=lambda: SimpleNamespace(process_id=lambda: 7),
                              timeout=1, _keyboard_safe=lambda control: failure != 'focus_lost')
    bounds = (0, 0, 250 if failure == 'clipped' else 1000, 600)
    monkeypatch.setitem(sys.modules, 'pywinauto.controls.hwndwrapper', SimpleNamespace(HwndWrapper=lambda handle: window))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(GetAncestor=lambda *args: 42,
                                                              GetForegroundWindow=lambda: 0,
                                                              IsWindowEnabled=lambda handle: False))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(GetWindowThreadProcessId=lambda handle: (0, 7)))
    monkeypatch.setattr(ui, '_activate_capture_window', lambda window: events.append('activate'))
    monkeypatch.setattr(ui, '_wait_capture_ready', lambda *args: bounds)
    monkeypatch.setattr(ui, '_capture_state', lambda window: (True, bounds))
    monkeypatch.setattr(calibration.time, 'sleep', lambda delay: None)
    if failure:
        with pytest.raises(ReviewRequired):
            calibration.capture_table(adapter, {'path': [{}]}, {})
    else:
        image, metadata = calibration.capture_table(adapter, {'path': [{}]}, {})
        assert image.size == (200, 120)
        assert metadata['foreground_verified_before_and_after'] is True
        assert events == ['activate', 'focus', '^{HOME}', 'capture', 'capture']
