import pytest

from fakturama_cash.document_fields import address_lines, document_addresses, document_values, read_address
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.item_table import item_values
from fakturama_cash.verification import require
from fakturama_cash.ui import UIAAdapter


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


def test_fakturama_company_contact_and_german_postcode_format():
    address = dict(name='Northstar Office GmbH', street='Friedrichstrasse 88',
                   zip='10117', city='Berlin', country='Germany',
                   additional_name=None, specification=None, district=None)
    contact = dict(company='Northstar Office GmbH', first_name='Mart', last_name='Klein')
    visible = 'Northstar Office GmbH\r\nMart Klein\r\nFriedrichstrasse 88\r\nDE-10117 Berlin\r\nGermany'
    require(read_address(visible, address, contact=contact), address, 'selected_addresses')


def test_shared_company_heading_and_distinct_delivery_postal_address(order):
    debtor = order.debtor
    original = debtor.model_dump_json()
    expected = document_addresses(debtor)
    contact = dict(company=debtor.company, first_name=debtor.first_name, last_name=debtor.last_name)
    observed = {}
    for field, address in (('invoice_address', debtor.billing), ('delivery_address', debtor.delivery)):
        visible = (f'{debtor.company}\r\n{debtor.first_name} {debtor.last_name}\r\n'
                   f'{address.street}\r\nDE-{address.zip} {address.city}\r\n{address.country}')
        observed[field] = read_address(visible, address.model_dump(), contact=contact)
    require(observed, expected, 'selected_addresses')
    assert observed['invoice_address']['street'] != observed['delivery_address']['street']
    assert expected['delivery_address']['name'] == debtor.company
    assert debtor.delivery.name != debtor.company
    assert debtor.model_dump_json() == original


def test_shared_heading_keeps_source_optional_postal_fields(order):
    debtor = order.debtor.model_copy(deep=True)
    debtor.delivery.additional_name = 'Loading bay'
    debtor.delivery.specification = 'Floor 2'
    debtor.delivery.district = 'West'
    expected = document_addresses(debtor)['delivery_address']
    assert expected['additional_name'] == 'Loading bay'
    assert expected['specification'] == 'Floor 2'
    assert expected['district'] == 'West'


def test_address_query_uses_the_selected_debtor_context(monkeypatch):
    adapter = UIAAdapter({}, desktop=object())
    address = dict(name='Company', street='Road', zip='00123', city='City', country='Germany')
    context = dict(input={'debtor': {'billing': address}},
                   selected_debtor=dict(company='Company', first_name='Mart', last_name='Klein'))
    monkeypatch.setattr(adapter, '_scalar', lambda *args: 'Company\nMart Klein\nRoad\nDE-00123 City\nGermany')
    result = adapter._read({'address_structure': '${input.debtor.billing}'}, context)
    require(result, address, 'selected_addresses')


@pytest.mark.parametrize('contact_line', ['Someone Else', 'Mart', 'Mart Klein\nExtra'])
def test_unverified_contact_lines_are_not_discarded(contact_line):
    visible = f'Company\n{contact_line}\nRoad\nDE-00123 City\nGermany'
    contact = dict(company='Company', first_name='Mart', last_name='Klein')
    with pytest.raises(ReviewRequired, match='unexpected lines'):
        read_address(visible, {}, contact=contact)


def test_company_contact_format_requires_verified_contact_context():
    with pytest.raises(ReviewRequired, match='unexpected lines'):
        read_address('Company\nMart Klein\nRoad\nDE-00123 City\nGermany', {})


def test_wrong_company_with_correct_contact_is_not_discarded():
    with pytest.raises(ReviewRequired, match='unexpected lines'):
        read_address('Other Company\nMart Klein\nRoad\nDE-00123 City\nGermany', {},
                     contact=dict(company='Company', first_name='Mart', last_name='Klein'))


def test_verified_contact_does_not_replace_changed_address_values():
    address = dict(name='Company', street='Expected road', zip='00123', city='City', country='Germany')
    result = read_address('Company\nMart Klein\nWrong road\nDE-00124 Other City\nGermany', address,
                          contact=dict(company='Company', first_name='Mart', last_name='Klein'))
    assert result['street'] == 'Wrong road' and result['zip'] == '00124'
    assert result['city'] == 'Other City'
    with pytest.raises(ReviewRequired, match='do not match'):
        require(result, address, 'selected_addresses')


@pytest.mark.parametrize('postal,country', [('FR-00123', 'Germany'), ('DE-00123', 'France'), ('DE-123', 'Germany')])
def test_unknown_or_conflicting_postal_prefix_is_not_normalized(postal, country):
    result = read_address(f'Buyer\nRoad\n{postal} City\n{country}', {})
    assert result['zip'] == postal


def test_contact_line_and_optional_postal_fields_are_kept_distinct():
    address = dict(name='Company', street='Road', zip='00123', city='City', country='Germany',
                   additional_name='Warehouse', specification='Floor 2', district='West')
    result = read_address('Company\nMart Klein\nWarehouse\nRoad\nFloor 2\nWest\nDE-00123 City\nGermany', address,
                          contact=dict(company='Company', first_name='Mart', last_name='Klein'))
    require(result, address, 'selected_addresses')


def test_contact_name_as_additional_name_is_not_removed_from_canonical_address():
    address = dict(name='Company', street='Road', zip='00123', city='City', country='Germany',
                   additional_name='Mart Klein')
    result = read_address('Company\nMart Klein\nRoad\n00123 City\nGermany', address,
                          contact=dict(company='Company', first_name='Mart', last_name='Klein'))
    assert result['additional_name'] == 'Mart Klein'


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
