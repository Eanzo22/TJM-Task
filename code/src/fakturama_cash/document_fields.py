"""Translate observed document fields without inventing missing UI values."""
import re

from .errors import ReviewRequired
from .normalize import amount, day


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


def read_address(text, structure):
    # Optional fields define the layout only. Values come from the visible Edit.
    if not text:
        return None
    lines = text.replace('\r\n', '\n').split('\n')
    fields = ['name']
    if structure.get('additional_name'):
        fields.append('additional_name')
    fields.append('street')
    fields.extend(name for name in ('specification', 'district') if structure.get(name))
    if len(lines) != len(fields) + 2:
        raise ReviewRequired('Document address has unexpected lines', stage='address_read', observed=text)
    postal = re.fullmatch(r'(\S+) (.+)', lines[-2])
    if not postal:
        raise ReviewRequired('Document postal line is unreadable', stage='address_read')
    result = dict(zip(fields, lines[:-2]))
    result.update(zip=postal[1], city=postal[2], country=lines[-1])
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
