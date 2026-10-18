import json
from pathlib import Path

import pytest
from PIL import Image

from fakturama_cash import cli
from fakturama_cash.errors import ReviewRequired, error_sources


def fail_review():
    raise ReviewRequired('Test guard', stage='test')


def fail_value():
    raise ValueError('Test number')


def wrapped_failure(*args, **kwargs):
    try:
        fail_value()
    except ValueError as exc:
        raise ReviewRequired('Wrapped test failure', stage='test') from exc


def test_review_reports_exact_raise_site_after_reraise():
    try:
        try:
            fail_review()
        except ReviewRequired:
            raise
    except ReviewRequired as exc:
        assert exc.details['origin'] == dict(file=str(Path(__file__).resolve()),
            line=fail_review.__code__.co_firstlineno + 1, function='fail_review')
        assert 'cause_origin' not in exc.details
        exc.details['safe_next_action'] = 'Preserved caller edit'
        assert exc.details['safe_next_action'] == 'Preserved caller edit'


def test_unraised_review_has_creation_site():
    error = ReviewRequired('Not raised yet')
    assert error.details['origin']['function'] == 'test_unraised_review_has_creation_site'
    assert error.details['origin']['file'] == str(Path(__file__).resolve())


def test_wrapped_error_reports_both_locations_without_locals():
    private_marker = 'DO NOT INCLUDE LOCAL VARIABLES'
    with pytest.raises(ReviewRequired) as caught:
        wrapped_failure()
    details = caught.value.details
    assert details['origin']['function'] == 'wrapped_failure'
    assert details['cause_origin'] == dict(file=str(Path(__file__).resolve()),
        line=fail_value.__code__.co_firstlineno + 1, function='fail_value', exception_type='ValueError')
    assert private_marker not in json.dumps(details)


def test_suppressed_exception_context_is_not_reported():
    try:
        try:
            fail_value()
        except ValueError:
            raise ReviewRequired('Independent guard') from None
    except ReviewRequired as exc:
        assert 'cause_origin' not in error_sources(exc)


@pytest.mark.parametrize('wrapped', [False, True])
def test_cli_errors_and_saved_reviews_include_origin(tmp_path, monkeypatch, capsys, wrapped):
    image = tmp_path / 'blank.png'
    Image.new('RGB', (20, 20), 'white').save(image)
    def unexpected(*args, **kwargs):
        fail_value()
    monkeypatch.setattr(cli, 'extract', wrapped_failure if wrapped else unexpected)
    assert cli.main(['validate', str(image), '--runs', str(tmp_path / 'runs'), '--quiet']) == 2
    output = capsys.readouterr()
    assert output.out == ''
    reported = json.loads(output.err)
    saved = json.loads(Path(reported['evidence']).read_text(encoding='utf-8'))
    assert reported['origin'] == saved['origin']
    assert reported['origin']['function'] == ('wrapped_failure' if wrapped else 'fail_value')
    assert Path(reported['origin']['file']).is_absolute()
    assert reported['origin']['line'] > 0
    if wrapped:
        assert reported['cause_origin'] == saved['cause_origin']
        assert reported['cause_origin']['function'] == 'fail_value'


def test_normal_preflight_review_reports_guard_not_exception_constructor(tmp_path, capsys):
    profile = tmp_path / 'partial.json'
    profile.write_text('{"calibrated": false}', encoding='utf-8')
    assert cli.main(['check-profile', str(profile), '--quiet']) == 2
    reported = json.loads(capsys.readouterr().err)
    assert Path(reported['origin']['file']).name == 'ui.py'
    assert reported['origin']['function'] == 'preflight'
