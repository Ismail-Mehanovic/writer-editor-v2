"""The file list window: every document, most recently edited first.
Up and Down pick one; Enter opens it, and the window becomes its editor."""

import document
import style

HEADER, DIVIDER, LIST_TOP, ROW = 40, 124, 144, 44  # the same header as editor.SPLIT_HEADER


class FileList:
    def __init__(self, folder):
        self.folder = folder
        self.selected = 0
        self.reload()

    def reload(self):
        self.documents = document.list_documents(self.folder)
        self.selected = min(self.selected, max(len(self.documents) - 1, 0))

    def handle(self, key):
        """Returns the path to open when Enter is pressed, otherwise None."""
        if key == 'up':
            self.selected = max(self.selected - 1, 0)
        elif key == 'down':
            self.selected = min(self.selected + 1, max(len(self.documents) - 1, 0))
        elif key == 'enter' and self.documents:
            return self.documents[self.selected][1]
        return None

    def draw(self, canvas, rect, focused, alone=False, full=True):
        """Draws the whole list in rect (it is short, so always all of it)."""
        x, y, w, h = rect
        pad = style.SPLIT_PADDING
        canvas.fill(x, y, w, h, style.PAGE)
        canvas.text(style.LABEL_FACE, x + pad, y + HEADER, 'FILES', style.LABEL, style.PAGE)
        canvas.fill(x, y + DIVIDER, w, 1, style.LINE)
        face, right = style.LIST_FACE, x + w - pad
        if not self.documents:
            canvas.text(face, x + pad, y + LIST_TOP + 28, 'No documents yet.', style.LABEL, style.PAGE, right)
            return
        rows = max((h - LIST_TOP - 16) // ROW, 1)
        top = max(0, self.selected - rows + 1)
        for i, (title, _) in enumerate(self.documents[top:top + rows]):
            row_y = y + LIST_TOP + i * ROW
            chosen = top + i == self.selected
            bg = style.SELECTED if chosen and focused else style.PAGE
            if bg != style.PAGE:
                canvas.rounded(x + pad - 12, row_y, w - 2 * pad + 24, ROW - 6, 8, bg, style.PAGE)
            colour = style.TITLE if chosen else style.TEXT
            canvas.text(face, x + pad, row_y + 27, title, colour, bg, right)
