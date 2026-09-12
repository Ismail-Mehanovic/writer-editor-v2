"""The file list window: every document, most recently edited first.
Up and Down pick one; Enter opens it, and the window becomes its editor."""

import document
import style


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

    def draw(self, screen, rect, focused, alone=False, upright=False):
        """Draws the list in rect. Returns None: a file list has no cursor."""
        y, x, h, w = rect
        style.fill(screen, y, x, h, w, style.PAGE)
        inner = w - 4
        screen.addnstr(y + 1, x + 2, 'FILES', inner, style.LABEL)
        rows = h - 3
        if not self.documents:
            screen.addnstr(y + 3, x + 2, 'No documents yet.', inner, style.LABEL)
            return
        top = max(0, self.selected - rows + 1)
        for i, (title, _) in enumerate(self.documents[top:top + rows]):
            chosen = top + i == self.selected
            attr = style.SELECTED if chosen and focused else style.TITLE if chosen else style.TEXT
            screen.addnstr(y + 3 + i, x + 2, (' ' + title).ljust(inner), inner, attr)
