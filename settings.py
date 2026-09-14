"""The settings: the size windows open at, and the typeface.

Esc twice (Esc for select mode, then Esc again) turns the chosen window
into this one. Up and Down pick a line, Left and Right change it, and
Backspace closes the window again. A change takes effect everywhere at
once and is written to a small file beside the documents, so it is still
there next time the Pi is switched on.
"""

import json
import os

import document
import style

FILE = '.settings.json'
ROWS = ('zoom', 'font')
LABELS = {'zoom': 'Text size', 'font': 'Typeface'}
ROW = 52  # a row's height
LONE_TOP, SPLIT_TOP = (72, 120), (40, 76)  # the SETTINGS label and the first row,
#                    below the page's top edge: with the screen to itself, or beside others


class Settings:
    """What the whole editor agrees on, and the file it is kept in."""

    def __init__(self, folder):
        self.path = os.path.join(folder, FILE)
        self.zoom, self.font = style.ZOOM_DEFAULT, style.FONT_DEFAULT
        try:
            with open(self.path, encoding='utf-8') as f:
                saved = json.load(f)
            if saved.get('zoom') in style.ZOOM_STEPS:
                self.zoom = saved['zoom']
            if saved.get('font') in style.FAMILIES:
                self.font = saved['font']
        except (OSError, ValueError, AttributeError):
            pass  # no file yet, or one that can't be read: the defaults stand
        style.use_font(self.font)

    def save(self):
        """Keeps the choices for next time. An error string, or None."""
        try:
            document.write_atomic(self.path, json.dumps({'zoom': self.zoom, 'font': self.font}))
        except OSError as e:
            return f'The settings could not be saved: {e}'
        return None


class SettingsWindow:
    """The window showing the settings. Like the file list it hands what
    happened back to the main loop, which is what applies it."""

    def __init__(self, settings):
        self.settings = settings
        self.selected = 0
        self.zoom = settings.zoom
        self.cursor_on = True  # nothing blinks here; the main loop sets it anyway

    @property
    def sizes(self):
        """The fonts and measurements at this window's zoom."""
        return style.sizes(self.zoom)

    # ---- keys

    def handle(self, key):
        """Acts on one key. Returns ('zoom', size), ('font', name) or
        ('close', None) for the main loop, or None."""
        if key in ('up', 'down'):
            self.selected = (self.selected + (1 if key == 'down' else -1)) % len(ROWS)
        elif key == 'backspace':
            return ('close', None)
        elif key in ('left', 'right', 'enter'):
            step = -1 if key == 'left' else 1
            if ROWS[self.selected] == 'zoom':
                self.settings.zoom = style.zoom_step(self.settings.zoom, step)
                return ('zoom', self.settings.zoom)
            order = style.FONT_ORDER
            self.settings.font = order[(order.index(self.settings.font) + step) % len(order)]
            return ('font', self.settings.font)
        return None

    def status(self):
        """What the status line says while this window has the focus."""
        return 'Up/Down: pick a setting    Left/Right: change it    Backspace: close'

    # ---- drawing

    def draw(self, canvas, rect, focused, alone=False, full=True, active=True):
        """Draws the whole window in rect: a centred page like a document
        when it has the screen to itself, the plain window beside others."""
        x, y, w, h = rect
        s = self.sizes
        face = s.LIST_FACE
        row_h, base, gap = s.px(ROW), s.px(33), s.px(12)
        lone = alone and w > s.PAGE_WIDTH
        if lone:
            px, pw, pad = x + (w - s.PAGE_WIDTH) // 2, s.PAGE_WIDTH, s.PADDING
            page_y = y + s.PAGE_TOP
            canvas.fill(x, y, w, h, style.BACKDROP)
            canvas.rounded(px, page_y, pw, y + h - page_y, s.RADIUS, style.BORDER, style.BACKDROP)
            canvas.rounded(px + 1, page_y + 1, pw - 2, y + h - page_y - 2, s.RADIUS - 1,
                           style.PAGE, style.BORDER)
        else:
            px, pw, pad, page_y = x, w, s.SPLIT_PADDING, y
            canvas.fill(x, y, w, h, style.PAGE)
        left, right = px + pad, px + pw - pad
        label_y, first_row = LONE_TOP if lone else SPLIT_TOP
        canvas.text(s.LABEL_FACE, left, page_y + s.px(label_y), 'SETTINGS',
                    style.LABEL, style.PAGE, right)
        for i, name in enumerate(ROWS):
            row_y = page_y + s.px(first_row) + i * row_h
            chosen = i == self.selected
            bg = style.SELECTED if chosen and focused else style.PAGE
            if bg != style.PAGE:
                canvas.rounded(left - s.px(12), row_y, right - left + s.px(24), row_h - s.px(8),
                               s.px(8), bg, style.PAGE)
            value, value_face = self._value(name, s)
            parts = [(value, value_face, style.TITLE if chosen else style.TEXT)]
            if chosen:  # the arrows show that Left and Right change it
                parts = [('‹', face, style.LABEL)] + parts + [('›', face, style.LABEL)]
            width = sum(f.width(t) for t, f, _ in parts) + gap * (len(parts) - 1)
            value_x = right - round(width)
            canvas.text(face, left, row_y + base, LABELS[name], style.LABEL, bg, value_x - gap)
            for text, text_face, colour in parts:
                value_x = canvas.text(text_face, value_x, row_y + base, text, colour, bg, right) + gap

    def _value(self, name, s):
        """What a setting says now, and the font to say it in: a typeface
        writes its own name, so you can see it before you choose it."""
        if name == 'zoom':
            return f'{round(self.settings.zoom * 100)}%', s.LIST_FACE
        family = self.settings.font
        return style.FAMILIES[family][0], style.sizes(self.zoom, family).LIST_FACE
