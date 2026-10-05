"""Compose the observed English Fakturama mappings into one reviewable profile.

Run from code/. The result stays uncalibrated until the complete recipes have
been checked live. Component JSON files remain the mapping sources.
"""
from copy import deepcopy
import json
from pathlib import Path


def replace_titles(value):
    titles = {'New Order': '${order_editor}', 'New Invoice': '${invoice_editor}',
              'New Debtor': '${debtor_editor}'}
    if isinstance(value, dict):
        return {k: titles.get(v, v) if k == 'title' and isinstance(v, str)
                else replace_titles(v) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_titles(v) for v in value]
    return value


def build():
    profile = dict(calibrated=False, window_title_re='^Fakturama - .*', timeout_seconds=120,
                   observation='2026-10-04: reviewed English/EUR UIA mappings; PO000003/INV000002 save/reopen verified. See handoff for clean-run evidence.',
                   actions={}, queries={})
    for name in ('observed', 'master-forms', 'definitions', 'selectors', 'documents'):
        component = json.loads(Path(f'config/{name}.partial.json').read_text(encoding='utf-8'))
        for section in ('actions', 'queries'):
            profile[section].update(replace_titles(component[section]))
    actions, queries = profile['actions'], profile['queries']
    for step in actions['fill_line']:
        step['layout'].update(header_width=1175,
            header_sha256='fdd3d7759cf205c22f5a5f5f01ef4d0858dd23bf6b86cc18134a1cb61f2120ef')
    queries['debtor_results']['clipboard_rows']['row_geometry']['header_sha256'] = [
        '828e11492faff348edba96a35135523c9248042b4ec8065b6db7164c00f1464f',
        '7bf3e914920c3b51bccdd414c00e8bdc2a95b4e7686601d0cd43b65ff4098806']

    def pane(kind):
        return [{'control_type': 'Pane', 'title': '${' + kind + '_editor}'}]

    def field(kind, typ, title, **kw):
        return pane(kind) + [dict(control_type=typ, title=title, **kw)]

    def tab(kind, title):
        return dict(operation='select_tab', path=field(kind, 'TabItem', title))

    # Prepare and close Preferences without saving settings.
    pref = [{'control_type': 'Window', 'title': 'Preferences'}]
    actions['inspect_environment'] = [
        dict(operation='select', path=[{'control_type': 'MenuItem', 'title': 'File'}]),
        dict(operation='select', path=[{'control_type': 'MenuItem', 'title': 'Preferences'}]),
        dict(operation='select', path=pref + [{'control_type': 'TreeItem', 'title': 'General'}])]
    queries['environment'] = {'fields': {'currency': {'path': pref + [{'control_type': 'Edit', 'title': 'Example'}],
                                                        'read': 'native_text', 'transform': 'currency'}}}
    actions['close_environment'] = [dict(operation='invoke', path=pref + [{'control_type': 'Button', 'title': 'Cancel'}],
                                          wait_absent=pref)]
    # Products dialog can accept a single filtered row before the workflow's
    # exact-match/OK checks. The observed Preferences tree item is Documents;
    # Document Settings is a Text heading inside that page, not a TreeItem.
    auto_accept = pref + [{'control_type': 'CheckBox',
        'title': 'immediately take over a clearly found item number'}]
    actions['inspect_product_selection_settings'] = [dict(operation='select',
        path=pref + [{'control_type': 'TreeItem', 'title': 'Documents'}])]
    queries['product_selection_settings'] = dict(fields={
        'auto_accept_single_product': dict(path=auto_accept, read='toggle')})
    actions['disable_product_auto_accept'] = [
        dict(operation='toggle', path=auto_accept, value=False),
        dict(operation='invoke', path=pref + [{'control_type': 'Button', 'title': 'Apply'}])]

    actions['activate_order'] = [dict(operation='select_tab', path=[{'control_type': 'TabItem', 'title': '${order_tab}'}])]
    # Fakturama 2.2.0's Navigation View New Contact omits force-new and can
    # reactivate an existing contact. The explicit New menu requests a draft.
    actions['new_debtor'] = [
        dict(operation='select', path=[{'control_type': 'MenuItem', 'title': 'New'}]),
        dict(operation='select', path=[{'control_type': 'MenuItem', 'title': 'New Debtor'}],
             wait_query='debtor_contact')]
    actions['fill_debtor'] = []
    for name in ('fill_debtor_contact', 'fill_debtor_billing_fields', 'set_billing_roles',
                 'add_delivery_address', 'set_delivery_roles', 'fill_debtor_delivery_fields', 'fill_debtor_misc'):
        recipe = deepcopy(actions[name])
        if name == 'fill_debtor_delivery_fields':
            for step in recipe:
                step['when'] = '${debtor_definition.separate_delivery}'
        # Payment is selected after contact fields and conditional term setup.
        actions['fill_debtor'].extend(step for step in recipe
            if not (name == 'fill_debtor_misc' and step.get('value') == '${debtor_definition.payment_method}'))
    actions['fill_debtor_payment'] = [tab('debtor', 'Miscellaneous'),
        dict(operation='select_option', path=field('debtor', 'ComboBox', 'Payment'),
             value='${debtor_definition.payment_method}')]
    actions['activate_debtor'] = [dict(operation='select_tab', path=[
        {'control_type': 'TabItem', 'title': '${debtor_tab}'}])]
    queries['debtor_methods'] = dict(prepare=[tab('debtor', 'Miscellaneous')],
        path=field('debtor', 'ComboBox', 'Payment'), read='options')
    queries['debtor'] = {'debtor_form': True}

    # Enter source recipient names in the document's editable address snapshot.
    actions['fill_order_addresses'] = []
    for role, label in (('billing', 'Invoice address'), ('delivery', 'Delivery address')):
        steps = [tab('order', label), dict(operation='type_address',
                 path=field('order', 'Edit', '', below_label={'control_type': 'TabItem', 'title': label}),
                 value='${input.debtor.' + role + '}', commit_path=field('order', 'Edit', 'Cust.Ref.'))]
        if role == 'delivery':
            for step in steps:
                step['when'] = '${separate_delivery}'
        actions['fill_order_addresses'].extend(steps)

    queries['items_raw']['clipboard_rows'].update(
        copy_scope='all_rows', empty_crop=True, empty_snapshot={'width': 1450, 'height': 50,
        'sha256': '121f07be6d69e47c15a8e14913eb3aa7b0aa901c0b883d543681b8de01928627'})
    queries['line'] = {**deepcopy(queries['items_raw']), 'row_transform': 'order_item', 'row_index': '${index}'}

    for kind in ('order', 'invoice'):
        header = 'order_header' if kind == 'order' else 'invoice_header'
        raw = deepcopy(queries['items_raw'])
        raw['path'] = field(kind, 'Pane', '', to_right_of='Items') + [{'control_type': 'Pane', 'direct': True}]
        if kind == 'invoice':
            raw['clipboard_rows'].pop('empty_snapshot')
            raw['clipboard_rows'].pop('empty_crop')
        raw['row_transform'] = 'order_item'
        queries[kind + '_items'] = raw
        for role, label in (('billing', 'Invoice address'), ('delivery', 'Delivery address')):
            query = dict(prepare=[tab(kind, label)], path=field(kind, 'Edit', '',
                         below_label={'control_type': 'TabItem', 'title': label}), read='native_text',
                         address_structure='${input.debtor.' + role + '}')
            if role == 'delivery':
                query.update(if_present=field(kind, 'TabItem', label), fallback_query=kind + '_billing')
            queries[kind + '_' + role] = query
        money = {}
        for output, label in (('net', 'Total Net'), ('vat', 'VAT'), ('total', 'Total'), ('discount', 'Discount')):
            money[output] = dict(path=field(kind, 'Edit', label), read='native_text', transform='decimal')
        money['shipping'] = dict(path=field(kind, 'Edit', '', to_right_of={'control_type': 'ComboBox', 'title': 'Shipping'}),
                                 read='native_text', transform='decimal')
        queries[kind + '_body'] = {'fields': {**money, 'items': raw,
            'invoice_address': queries[kind + '_billing'], 'delivery_address': queries[kind + '_delivery']}}
        queries[kind] = {'merge_queries': [header, kind + '_body']}
    # New Order starts in Gross mode; its initial read only needs the number.
    # Total Net appears after the mapped header switches to Net.
    queries['order']['initial_draft'] = 'order_header'
    queries['order_addresses'] = {'fields': {'invoice_address': queries['order_billing'],
                                            'delivery_address': queries['order_delivery']}}
    payment = queries['invoice_payment_fields']['fields']
    for name in ('payment_date', 'value'):
        payment[name]['when_checked'] = payment['paid']
    payment['value']['read'] = 'native_text'
    queries['invoice']['merge_queries'].append('invoice_payment_fields')
    actions['fill_order_totals'] = [
        dict(operation='type_text', path=field('order', 'Edit', 'Discount'), value='0', transform='decimal',
             decimal_separator='.', read='native_text', commit_path=field('order', 'Edit', 'Cust.Ref.')),
        dict(operation='select_option', path=field('order', 'ComboBox', 'Shipping'), value='Free of shipping costs'),
        dict(operation='type_text', path=field('order', 'Edit', '', to_right_of={'control_type': 'ComboBox', 'title': 'Shipping'}),
             value='0', transform='decimal', decimal_separator=',', read='native_text',
             commit_path=field('order', 'Edit', 'Cust.Ref.'))]

    # Documents copy omits a source-order relationship number; customer is a
    # rendered company/contact string. Keep the observed fields intact.
    doc_path = [{'control_type': 'Pane', 'title': 'Documents'},
                {'control_type': 'Pane', 'direct': True},
                {'control_type': 'Pane', 'direct': True},
                {'control_type': 'Pane', 'direct': True, 'below_label': 'Search:'}]
    queries['documents_raw'] = {'path': doc_path, 'clipboard_rows': {
        'columns': ['type_raw', 'no', 'date_raw', 'customer', 'reference', 'state_raw', 'total', 'printed_raw'],
        'copy_scope': 'all_rows', 'format': 'raw_tsv', 'keyboard_selection': 'ctrl_home_down_double_click',
        'empty_snapshot': {'width': 1340, 'height': 304,
                           'sha256': 'fe6d53d6e1deb547882991eb0936416487676d0d268752b8892b56c9960da737'},
        'row_geometry': {'width': 1340, 'header_height': 25, 'row_height': 25, 'column_x': 187,
                         # Reviewed Documents headers with/without the scrollbar
                         # allocation. Both keep x187 inside the Document column.
                         'header_sha256': [
                             '13957440fdaa2bb1065b67d725650e970505de2244bda8de13a82334939addb3',
                             'b19c98b06aae4d19a15cb8be1a158b54bff53e9a84d93502b7744db6180ff101']}}}
    categories = []
    for category in ('Orders', 'Invoices'):
        query = 'documents_' + category.lower()
        categories.append(query)
        queries[query] = {**deepcopy(queries['documents_raw']), 'row_transform': 'document',
            'prepare': [dict(operation='select_tree', path=[{'control_type': 'Pane', 'title': 'Documents'},
                                                          {'control_type': 'TreeItem', 'title': category}])]}
    queries['documents'] = {'concat_queries': categories}
    queries['documents_raw']['prepare'] = [dict(operation='select_tree', path=[
        {'control_type': 'Pane', 'title': 'Documents'}, {'control_type': 'TreeItem', 'title': 'Invoices'}])]
    search_path = [{'control_type': 'Pane', 'title': 'Documents'}, {'control_type': 'Edit', 'to_right_of': 'Search:'}]
    queries['document_search'] = {'path': search_path, 'read': 'native_text'}
    actions['open_documents'][0]['wait_query'] = 'document_search'
    actions['clear_document_search'] = [dict(operation='type_text', path=search_path, value='', read='native_text',
                                              commit_path=doc_path)]
    actions['open_documents'].extend(actions['clear_document_search'])
    actions['reopen_invoice'] = [
        dict(operation='select_tab', path=[{'control_type': 'TabItem', 'title': '${invoice_no}'}]),
        dict(operation='close_clean_editor', path=field('invoice', 'Edit', 'Cust.Ref.'),
             tab_path=[{'control_type': 'TabItem', 'title': '${invoice_no}', 'selected': True}], wait_absent=pane('invoice')),
        dict(operation='type_text', path=search_path, value='${invoice_no}', read='native_text', commit_path=doc_path),
        dict(operation='open_document_row', query='documents_raw', number='${invoice_no}')]
    return profile


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibrated', action='store_true',
                        help='Confirm component mapping calibration; does not claim a successful end-to-end run')
    args = parser.parse_args()
    target = Path('config/live-profile.json')
    profile = build()
    profile['calibrated'] = args.calibrated
    target.write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
    print(f'Built {target}; calibrated={args.calibrated}.')
