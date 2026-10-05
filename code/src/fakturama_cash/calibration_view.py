"""Interactive review of captured tables; clicks are on images, never Fakturama."""
from .errors import ReviewRequired


def review_image(image, title, *, empty=False, items=False):
    import tkinter as tk
    from tkinter import messagebox
    from PIL import ImageTk

    result = None
    root = tk.Tk()
    root.title(title)
    # Keep native pixels so small fonts and one-pixel boundaries stay readable
    # on narrower screens. Scroll the captured image, never the live app.
    photo = ImageTk.PhotoImage(image)
    instruction = tk.StringVar()
    tk.Label(root, textvariable=instruction, wraplength=1000, justify='left').pack(padx=12, pady=8)
    frame = tk.Frame(root)
    frame.pack(padx=12)
    canvas = tk.Canvas(frame, width=min(image.width, root.winfo_screenwidth() - 100),
                       height=min(image.height, max(100, root.winfo_screenheight() - 360)),
                       scrollregion=(0, 0, image.width, image.height), highlightthickness=0)
    canvas.grid(row=0, column=0)
    horizontal = tk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
    vertical = tk.Scrollbar(frame, orient='vertical', command=canvas.yview)
    horizontal.grid(row=1, column=0, sticky='ew')
    vertical.grid(row=0, column=1, sticky='ns')
    canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
    canvas.create_image(0, 0, anchor='nw', image=photo)

    points = {}
    steps = [('header_height', 'Click the first pixel BELOW the table header divider.'),
             ('first_row_bottom', 'Click the first pixel BELOW the FIRST data row divider.'),
             ('column_x', 'Click inside a data cell in the first row (away from borders).')]
    if items:
        steps = steps[:2] + [
            ('header_width', 'Click the RIGHT edge of the last data heading (Total), before the unused header tail.'),
            ('quantity', 'Click the centre of the Quantity cell in the first row.'),
            ('name', 'Click the centre of the Name cell in the first row.'),
            ('vat', 'Click the centre of the VAT cell in the first row.'),
            ('unit_price', 'Click the centre of the Unit Price cell in the first row.'),
            ('discount', 'Click the centre of the Discount cell in the first row.')]
    count = tk.StringVar(value='1' if items else '')
    confirmed = tk.BooleanVar()
    if empty:
        instruction.set('Review this captured table. Confirm only if it has NO data rows. '
                        'A populated table must never be recorded as an empty-table reference.')
    else:
        instruction.set(steps[0][1])
        tk.Label(root, text='Total rows in these results, INCLUDING rows below the visible area:').pack(pady=(8, 0))
        tk.Entry(root, textvariable=count, width=12).pack()
    tk.Checkbutton(root, variable=confirmed,
                   text='I checked this is an empty table.' if empty else
                        'I checked the column order and the total row count against Fakturama.').pack(pady=8)
    status = tk.StringVar()
    tk.Label(root, textvariable=status, wraplength=1000).pack()

    def clicked(event):
        if empty or len(points) == len(steps):
            return
        key = steps[len(points)][0]
        coordinate = round(canvas.canvasy(event.y) if key in ('header_height', 'first_row_bottom') else canvas.canvasx(event.x))
        points[key] = coordinate
        if key in ('header_height', 'first_row_bottom'):
            canvas.create_line(0, coordinate, image.width, coordinate, fill='red', width=1)
        else:
            canvas.create_line(coordinate, 0, coordinate, image.height, fill='red', width=1)
        status.set(', '.join(f'{k}={v}' for k, v in points.items()))
        instruction.set(steps[len(points)][1] if len(points) < len(steps) else
                        'Review the marked boundaries and positions, enter the total row count, then accept.')

    def reset():
        points.clear()
        canvas.delete('all')
        canvas.create_image(0, 0, anchor='nw', image=photo)
        status.set('')
        if not empty:
            instruction.set(steps[0][1])

    def accept():
        nonlocal result
        if not confirmed.get():
            messagebox.showerror('Review required', 'Check the review checkbox before accepting.', parent=root)
            return
        if empty:
            result = {'empty_confirmed': True}
        else:
            if len(points) != len(steps) or not count.get().isascii() or not count.get().isdecimal() or int(count.get()) < 1:
                messagebox.showerror('Review required', 'Mark every requested point and enter a positive total row count.', parent=root)
                return
            header, bottom = points['header_height'], points['first_row_bottom']
            if not 0 < header < bottom <= image.height:
                messagebox.showerror('Review required', 'Header and first-row boundaries are invalid. Reset the marks.', parent=root)
                return
            if any(not 0 < v < image.width for k, v in points.items()
                   if k not in ('header_height', 'first_row_bottom')):
                messagebox.showerror('Review required', 'Column positions must be inside the table.', parent=root)
                return
            result = {**points, 'row_height': bottom - header, 'expected_count': int(count.get()),
                      'columns_confirmed': True}
        root.destroy()

    buttons = tk.Frame(root)
    buttons.pack(pady=10)
    tk.Button(buttons, text='Accept reviewed capture', command=accept).pack(side='left', padx=5)
    if not empty:
        tk.Button(buttons, text='Reset marks', command=reset).pack(side='left', padx=5)
    tk.Button(buttons, text='Cancel calibration', command=root.destroy).pack(side='left', padx=5)
    canvas.bind('<Button-1>', clicked)
    root.mainloop()
    if result is None:
        raise ReviewRequired('Calibration cancelled; output profile was not changed', stage='calibration')
    return result
