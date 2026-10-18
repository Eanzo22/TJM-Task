"""Close only the verified unsaved Debtor when its payment list is stale."""
from .clipboard_table import focus_table
from .errors import ReviewRequired


def _native_save_list(control):
    from pywinauto.controls.common_controls import ListViewWrapper
    if control.class_name() != 'SysListView32' or not control.handle:
        raise ReviewRequired('Save Parts list does not support native checkbox read-back', stage='debtor_payment')
    return ListViewWrapper(control.handle)


def discard_draft(adapter, control, step, context):
    tab = adapter.find(step['tab_path'], context)
    if (context.get('debtor_editor') != 'New Debtor' or tab.window_text() != '*New Debtor'
            or not tab.is_selected() or not step.get('wait_absent')):
        raise ReviewRequired('Only the selected unsaved New Debtor may be refreshed', stage='debtor_payment')
    focus_table(control, lambda: adapter._keyboard_safe(control))
    if not adapter._keyboard_safe(control):
        raise ReviewRequired('Debtor focus changed before close', stage='debtor_payment')
    control.type_keys('^w', set_foreground=False, pause=0.05)

    # Observed Save Parts dialog defaults to saving. Uncheck only its single
    # New Debtor entry; never accept a dialog containing the Order or other tabs.
    dialog = step['save_dialog']
    table = adapter.find(dialog + [{'control_type': 'List', 'title': 'Select the parts to save:'}], context)
    native = _native_save_list(table)
    if native.item_count() != 1 or native.get_item(0).text() != 'New Debtor':
        raise ReviewRequired('Save Parts must contain only New Debtor', stage='debtor_payment')
    if native.get_item(0).is_checked():
        focus_table(table, lambda: adapter._keyboard_safe(table))
        for key in ('{HOME}', '{SPACE}'):
            if not adapter._keyboard_safe(table):
                raise ReviewRequired('Save Parts focus changed', stage='debtor_payment')
            table.type_keys(key, set_foreground=False, pause=0.05)
    # Read the native checkbox state; selection alone does not mean unchecked.
    adapter._wait_for(lambda: not native.get_item(0).is_checked(), 'Debtor still selected for saving')
    if native.item_count() != 1 or native.get_item(0).text() != 'New Debtor':
        raise ReviewRequired('Save Parts contents changed', stage='debtor_payment')
    adapter.find(dialog + [{'control_type': 'Button', 'title': 'OK'}], context).invoke()
    adapter._wait_absent(dialog, context)
