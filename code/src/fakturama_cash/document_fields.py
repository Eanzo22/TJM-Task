"""Translate observed document fields without inventing missing UI values."""
import re

from .errors import ReviewRequired
from .normalize import amount, day, key


def document_addresses(debtor):
    """Map the brief's shared Debtor Company and per-role postal fields.

    Steps 2.6-2.8 set Company/contact once, then assign postal addresses to
    Invoice/Delivery roles. Source address-block names remain in the input;
    they are not separate Company fields in the Fakturama address editor.
    """
    return {field: {**address.model_dump(mode='json'), 'name': debtor.company}
            for field, address in (('invoice_address', debtor.billing),
                                   ('delivery_address', debtor.delivery))}


def address_lines(address):
    lines = [address['name']]
    if address.get('additional_name'):
        lines.append(address['additional_name'])
    lines.append(address['street'])
    for name in ('specification', 'district'):
        if address.get(name):
            lines.append(address[name])
    lines.extend([f"{address['zip']} {address['city']}", address['country']])
    if any(not isinstance(line, str) or not line or any(ord(c) < 32 for c in line) for line in lines):
        raise ReviewRequired('Address contains unsupported line breaks', stage='address_entry')
    return lines


def read_address(text, structure, *, contact=None):
    # Optional fields define the layout only. Values come from the visible Edit.
    if not text:
        return None
    lines = text.replace('\r\n', '\n').split('\n')
    fields = ['name']
    if structure.get('additional_name'):
        fields.append('additional_name')
    fields.append('street')
    fields.extend(name for name in ('specification', 'district') if structure.get(name))
    # Fakturama can render the selected contact beneath the Company. This is
    # presentation of an already verified contact, not an extra postal field.
    # Accept it only with matching company and full contact name; never discard
    # an arbitrary extra line or replace the observed recipient with source data.
    if len(lines) == len(fields) + 3 and contact:
        company = contact.get('company')
        first, last = contact.get('first_name'), contact.get('last_name')
        if (company and first and last and key(lines[0]) == key(company)
                and key(lines[1]) == key(f'{first} {last}')):
            lines = [lines[0], *lines[2:]]
    if len(lines) != len(fields) + 2:
        raise ReviewRequired('Document address has unexpected lines', stage='address_read', observed=text)
    postal = re.fullmatch(r'(\S+) (.+)', lines[-2])
    if not postal:
        raise ReviewRequired('Document postal line is unreadable', stage='address_read')
    result = dict(zip(fields, lines[:-2]))
    postcode, country = postal[1], lines[-1]
    # The observed German address formatter adds DE- to the postal code. Only
    # normalize that known country/prefix pair; other prefixes stay visible to
    # the subsequent exact-value check, including conflicting country codes.
    if key(country) == key('Germany') and re.fullmatch(r'DE-\d{5}', postcode):
        postcode = postcode[3:]
    result.update(zip=postcode, city=postal[2], country=country)
    for field in ('additional_name', 'specification', 'district'):
        result.setdefault(field, None)
    return result


def document_values(row):
    types = {'ICON_ORDER': 'Order', 'ICON_INVOICE': 'Invoice'}
    states = {'COMMAND_ORDER_PENDING': 'open', 'COMMAND_CHECKED': 'paid',
              'COMMAND_UNCHECKED': 'unpaid'}
    match = re.fullmatch(r'\w{3} (\w{3}) (\d{2}) \d{2}:\d{2}:\d{2} [A-Z]+ (\d{4})', row['date_raw'])
    if row['type_raw'] not in types or row['state_raw'] not in states or not match:
        raise ReviewRequired('Unrecognized document-list format', stage='documents_read', observed=row)
    return {**row, 'type': types[row['type_raw']], 'state': states[row['state_raw']],
            'date': day(f'{match[1]} {match[2]}, {match[3]}').isoformat(),
            'total': str(amount(row['total']))}
