import pytest

from fakturama_cash.document_fields import address_lines, document_values, read_address
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.item_table import item_values


def test_address_reads_actual_values_with_optional_lines():
    layout = dict(name='Original', additional_name='Warehouse', street='Original road',
                  specification='Floor 2', district='Central', zip='10000', city='Berlin', country='Germany')
    visible = 'Changed recipient\r\nChanged warehouse\r\nNew road\r\nFloor 3\r\nWest\r\n00123 New City\r\nGermany'
    result = read_address(visible, layout)
    assert result['name'] == 'Changed recipient'
    assert result['specification'] == 'Floor 3'
    assert result['zip'] == '00123'
    assert address_lines(result) == visible.replace('\r\n', '\n').split('\n')


def test_unexpected_address_line_is_not_silently_discarded():
    with pytest.raises(ReviewRequired, match='unexpected lines'):
        read_address('Buyer\nRoad\nExtra\n10000 City\nGermany', {})


def test_address_rejects_embedded_shortcuts_and_line_breaks():
    value = dict(name='Buyer\nInjected', street='Road', zip='10000', city='City', country='Germany')
    with pytest.raises(ReviewRequired):
        address_lines(value)


def test_document_date_and_customer_are_observed_without_guessing_company():
    row = dict(type_raw='ICON_INVOICE', no='INV000001',
               date_raw='Sun Oct 04 00:00:00 EEST 2026',
               customer='Company, Inc., Alex Example', reference='TEST',
               state_raw='COMMAND_CHECKED', total='42.84', printed_raw='null')
    result = document_values(row)
    assert result['date'] == '2026-10-04'
    assert result['customer'] == row['customer']
    assert result['type'] == 'Invoice' and result['state'] == 'paid'
    assert 'company' not in result


def test_item_copy_discount_fraction_matches_positive_source_discount():
    row = dict(sku='TEST', name='Chair', quantity='2.0', unit_price='EUR 20',
               vat_raw='VAT taxValue: [0.19] name: VAT 19%', discount_raw='-0.1', line_price='EUR 36')
    result = item_values(row)
    assert result['discount_percent'] == '10.0'
    assert result['vat_percent'] == '19.00'
    assert result['source_net'] == '36'
