"""The file list window: the folders and documents in one folder, as
plainly as possible.

Up and Down pick a row. Enter opens a document (the window becomes its
editor) or goes into a folder (marked ›); the status line shows where
you are (crumbs()), and inside a folder the first row, '‹ Back to ...',
leads out. Ctrl+F makes a new folder and Ctrl+D a new, empty document,
both right here and without opening anything. Tab picks the chosen
document or folder up to move it: Enter on a folder or on '‹ Back to ...'
puts it there, Right and Left go into and out of folders on the way, and
Tab again cancels. Backspace asks before deleting; deleted things go to
the hidden .trash folder, so they can still be fished out from the shell.
"""

import os

import document
import keys
import style

HEADER, DIVIDER, LIST_TOP, ROW = 40, 124, 144, 44  # lines up with editor.SPLIT_HEADER
NEW_KEYS = {'ctrl-f': 'folder', 'ctrl-d': 'document'}


def _title(path):
    name = os.path.basename(path)
    return name if os.path.isdir(path) else os.path.splitext(name)[0]


class FileList:
    def __init__(self, root, folder=None):
        self.root = root
        self.folder = folder or root
        self.rows, self.selected = [], 0
        self.moving = None    # the path picked up with Tab
        self.naming = None    # while a new name is typed: [kind, text so far]
        self.confirm = None   # while asking about a delete: 0 Cancel, 1 Delete
        self.cursor_on = True  # the name cursor, off for half of every blink
        self.reload()

    def reload(self, select=None):
        """Reads the folder again, keeping the choice on the same row, or
        on the row for select (a path)."""
        if not os.path.isdir(self.folder):
            self.folder = self.root
        keep = select or (self.rows[self.selected][2] if self.rows else None)
        self.rows = []
        if self.folder != self.root:
            parent = os.path.dirname(self.folder)
            self.rows.append(('back', _title(parent), parent))
        self.rows += [('folder', n, p) for n, p in document.list_folders(self.folder)]
        self.rows += [('document', t, p) for t, p in document.list_documents(self.folder)]
        paths = [row[2] for row in self.rows]
        self.selected = (paths.index(keep) if keep in paths
                         else max(0, min(self.selected, len(self.rows) - 1)))

    def modal(self):
        """True while a question or a new name is open: it takes every key."""
        return self.confirm is not None or self.naming is not None

    # ---- keys

    def handle(self, key):
        """Acts on one key. Returns ('open', path), ('moved', old, new),
        ('deleted', path) or ('message', text) for the main loop, or None."""
        if self.confirm is not None:
            return self._confirm_key(key)
        if self.naming is not None:
            return self._name_key(key)
        if key in NEW_KEYS and not self.moving:
            self.naming = [NEW_KEYS[key], '']
            return None
        if not self.rows:
            return None
        kind, _, path = self.rows[self.selected]
        if key == 'up':
            self.selected = max(self.selected - 1, 0)
        elif key == 'down':
            self.selected = min(self.selected + 1, len(self.rows) - 1)
        elif key == 'right' and kind == 'folder':
            self._go(path)
        elif key == 'left' and self.folder != self.root:
            self._go(os.path.dirname(self.folder), came_from=self.folder)
        elif key == 'tab':
            self.moving = None if self.moving else path if kind in ('folder', 'document') else None
        elif key == 'enter' and self.moving and kind in ('folder', 'back'):
            return self._drop(path)
        elif key == 'enter' and kind in ('folder', 'back'):
            self._go(path, came_from=self.folder if kind == 'back' else None)
        elif key == 'enter' and kind == 'document' and not self.moving:
            return ('open', path)
        elif key == 'backspace' and kind in ('folder', 'document') and not self.moving:
            self.confirm = 0
        return None

    def _go(self, folder, came_from=None):
        self.folder, self.selected = folder, 0
        self.reload(select=came_from)

    def _drop(self, destination):
        source, self.moving = self.moving, None
        if os.path.dirname(source) == destination:
            return ('message', 'It is already there.')
        if destination == source or destination.startswith(source + os.sep):
            return ('message', 'A folder can\'t go inside itself.')
        new_path = document.move(source, destination)
        self.reload()
        return ('moved', source, new_path)

    def _confirm_key(self, key):
        if key == 'right':
            self.confirm = 1
        elif key == 'left':
            self.confirm = 0
        elif key in ('enter', 'backspace') and self.confirm == 1:
            path, self.confirm = self.rows[self.selected][2], None
            document.trash(path, self.root)
            self.reload()
            return ('deleted', path)
        else:
            self.confirm = None  # any other key keeps it
        return None

    def _name_key(self, key):
        kind, text = self.naming
        if key == 'enter':
            self.naming = None
            name = document.clean_title(text)
            if name:
                make = document.make_folder if kind == 'folder' else document.create_document
                self.reload(select=make(self.folder, name))
        elif key == 'backspace':
            self.naming[1] = text[:-1]
        elif keys.is_text(key):
            self.naming[1] = text + key
        else:
            self.naming = None  # any other key: nothing is made
        return None

    def status(self):
        """What the status line says while this list has the focus."""
        if self.confirm is not None:
            return 'Right: choose Delete, then Enter    any other key: keep it'
        if self.naming is not None:
            return f'Type the new {self.naming[0]}\'s name, then press Enter.'
        if self.moving:
            return (f'Moving "{_title(self.moving)}": pick a folder and press Enter'
                    '    Right/Left: in and out of folders    Tab: cancel')
        return 'Enter: open   Tab: move   Backspace: delete   Ctrl+F: new folder   Ctrl+D: new document'

    # ---- drawing

    def draw(self, canvas, rect, focused, alone=False, full=True):
        """Draws the whole list in rect (it is short, so always all of it)."""
        x, y, w, h = rect
        pad, face = style.SPLIT_PADDING, style.LIST_FACE
        right = x + w - pad
        canvas.fill(x, y, w, h, style.PAGE)
        canvas.text(style.LABEL_FACE, x + pad, y + HEADER, 'FILES', style.LABEL, style.PAGE)
        canvas.fill(x, y + DIVIDER, w, 1, style.LINE)

        rows, top = max((h - LIST_TOP - 16) // ROW, 1), y + LIST_TOP
        if self.naming is not None:  # the name being typed gets its own row
            self._draw_name(canvas, x + pad, top, right)
            rows, top = max(rows - 1, 1), top + ROW
        elif not self.rows:
            canvas.text(face, x + pad, top + 27, 'Nothing here yet.    Ctrl+D: new document',
                        style.LABEL, style.PAGE, right)
        first = max(0, self.selected - rows + 1)
        for i, (kind, name, path) in enumerate(self.rows[first:first + rows]):
            row_y = top + i * ROW
            chosen = first + i == self.selected and self.naming is None
            bg = style.SELECTED if chosen and focused else style.PAGE
            if bg != style.PAGE:
                canvas.rounded(x + pad - 12, row_y, w - 2 * pad + 24, ROW - 6, 8, bg, style.PAGE)
            label, colour = name, style.TITLE if chosen else style.TEXT
            if kind == 'back':
                label, colour = f'‹   Back to {name}', style.LABEL
            if path == self.moving:
                label, colour = f'{name}  (moving)', style.LABEL
            canvas.text(face, x + pad, row_y + 27, label, colour, bg, right - 24)
            if kind == 'folder':
                canvas.text(face, right - 10, row_y + 27, '›', style.LABEL, bg)
        if self.confirm is not None:
            self._draw_confirm(canvas, rect)

    def _draw_name(self, canvas, x, row_y, right):
        """The row where a new folder's or document's name is typed."""
        face = style.LIST_FACE
        canvas.rounded(x - 12, row_y, right - x + 24, ROW - 6, 8, style.SELECTED, style.PAGE)
        end = canvas.text(face, x, row_y + 27, f'New {self.naming[0]}:  ', style.LABEL, style.SELECTED, right)
        end = canvas.text(face, end, row_y + 27, self.naming[1], style.TITLE, style.SELECTED, right)
        if self.cursor_on:
            canvas.fill(round(end) + 2, row_y + 27 - face.ascent + 2, style.CURSOR_WIDTH,
                        face.ascent + face.descent - 2, style.TITLE)

    def crumbs(self):
        """Where this list is, for the status line: ['writing', 'Kapitel']."""
        inside = os.path.relpath(self.folder, self.root)
        return [_title(self.root)] + (inside.split(os.sep) if inside != '.' else [])

    def _draw_confirm(self, canvas, rect):
        """The card that asks before deleting: Cancel or Delete."""
        x, y, w, h = rect
        kind, name, _ = self.rows[self.selected]
        cw, ch = min(560, w - 40), 196
        cx, cy = x + (w - cw) // 2, y + (h - ch) // 2
        canvas.rounded(cx, cy, cw, ch, 12, style.BORDER, style.PAGE)
        canvas.rounded(cx + 1, cy + 1, cw - 2, ch - 2, 11, style.RAISED, style.BORDER)
        right = cx + cw - 28
        canvas.text(style.ROW_STYLES[3][0], cx + 28, cy + 56, f'Delete “{name}”?', style.TITLE, style.RAISED, right)
        note = ('The folder and everything in it go to the trash.' if kind == 'folder'
                else 'It goes to the trash folder.')
        canvas.text(style.STATUS_FACE, cx + 28, cy + 88, note, style.LABEL, style.RAISED, right)
        gap = 12
        bw, bh = min(120, (cw - 56 - gap) // 2), 44
        by = cy + ch - bh - 24
        for i, label in enumerate(('Cancel', 'Delete')):
            bx = right - (2 - i) * bw - (1 - i) * gap
            chosen = self.confirm == i
            bg = (style.DANGER if i else style.SELECTED) if chosen else style.RAISED
            canvas.rounded(bx, by, bw, bh, 8, bg if chosen else style.LINE, style.RAISED)
            if not chosen:
                canvas.rounded(bx + 1, by + 1, bw - 2, bh - 2, 7, style.RAISED, style.LINE)
            text_x = bx + (bw - style.LIST_FACE.width(label)) / 2
            canvas.text(style.LIST_FACE, text_x, by + 29, label,
                        style.TITLE if chosen else style.LABEL, bg, bx + bw)
