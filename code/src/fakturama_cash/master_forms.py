"""Combine live-observed contact form groups and verify address roles."""
from .errors import ReviewRequired


def debtor_values(adapter, context):
    def read(name):
        return adapter._read(adapter.profile['queries'][name], context)

    contact = read('debtor_contact')
    if 'debtor_definition' not in context:
        return contact  # New draft: only its proposed ID is needed before filling.
    misc = read('debtor_misc')
    billing = read('debtor_billing_fields')
    role_path = [{'control_type': 'Pane', 'title': '${debtor_editor}'},
                 {'control_type': 'Edit', 'title': '', 'to_right_of': 'address type'}]
    billing_roles = adapter._scalar({'path': role_path, 'read': 'native_text'}, context)
    extra_path = [{'control_type': 'Pane', 'title': '${debtor_editor}'},
                  {'control_type': 'TabItem', 'title': 'additional address #1'}]
    try:
        adapter._find_once(extra_path, context)
        separate = True
    except LookupError:
        separate = False
    delivery = read('debtor_delivery_fields') if separate else dict(billing)
    delivery_roles = adapter._scalar({'path': role_path, 'read': 'native_text'}, context)
    if separate:
        valid = billing_roles == 'Invoice address' and delivery_roles == 'Delivery address'
    else:
        valid = all(name in billing_roles for name in ('Invoice address', 'Delivery address'))
    if not valid:
        raise ReviewRequired('Debtor address roles do not match', stage='debtor_roles',
                             observed={'billing': billing_roles, 'delivery': delivery_roles})
    result = {**contact, **misc, 'email': billing.pop('email'), 'telephone': billing.pop('telephone'),
              'separate_delivery': separate}
    if delivery.pop('email') != result['email'] or delivery.pop('telephone') != result['telephone']:
        raise ReviewRequired('Delivery contact details do not match billing', stage='debtor_contact')
    for address in (billing, delivery):
        for field in ('additional_name', 'specification', 'district'):
            address[field] = address[field] or None
    return {**result, 'billing': billing, 'delivery': delivery}
