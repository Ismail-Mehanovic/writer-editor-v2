"""The editor window: a document's title above its body.

The body wraps between words and scrolls. Lines starting with '# ', '## '
or '### ' are headings. A new document starts in the title, and its body
can't be reached until the title has text. With the whole screen to itself
the editor is a centred page; beside other windows it fills its window.
"""

import curses

import cursor_font
import document
import keys
import style

PAGE_WIDTH = 72     # a lone editor's page, centred on the screen
PADDING = 3         # page edge to text, on the lone page
SPLIT_PADDING = 2   # window edge to text, beside other windows
BODY_TOP = 5        # rows above the body: space, label, title, line, space
MOVE_KEYS = ('left', 'right', 'up', 'down', 'home', 'end', 'pgup', 'pgdn')


def wrap(line, width):
    """Where each screen row of line starts, breaking between words."""
    starts = [0]
    while len(line) - starts[-1] > width:
        start = starts[-1]
        space = line.rfind(' ', start, start + width + 1)
        starts.append(space + 1 if space >= start else start + width)
    return starts


def heading_level(line):
    """1, 2 or 3 for lines starting '# ', '## ' or '### '; otherwise 0."""
    marks = len(line) - len(line.lstrip('#'))
    return marks if 1 <= marks <= 3 and line[marks:marks + 1] == ' ' else 0


class Editor:
    def __init__(self, doc):
        self.doc = doc
        self.title = doc.title        # the title as it is being typed
        self.in_title = not doc.title
        self.tx = len(self.title)     # cursor position in the title
        self.cy = self.cx = 0         # cursor line and column in the body
        self.want = 0                 # column within a row that Up/Down aim for
        self.top = (0, 0)             # first line and row shown
        self.width, self.rows = 66, 19  # text size, set when drawn

    def words(self):
        return sum(len(line.split()) for line in self.doc.lines)

    # ---- keys

    def handle(self, key):
        """Acts on one key. Returns a message for the status line, or None."""
        return self._title_key(key) if self.in_title else self._body_key(key)

    def _title_key(self, key):
        t, x = self.title, self.tx
        if key in ('enter', 'down'):
            wanted = document.clean_title(t)
            if not wanted:
                return 'Type a title first.'
            self.title = self.doc.set_title(wanted)
            self.tx, self.in_title = len(self.title), False
            if self.title != wanted:
                return f'"{wanted}" was taken, so this is "{self.title}".'
        elif key == 'left':
            self.tx = max(x - 1, 0)
        elif key == 'right':
            self.tx = min(x + 1, len(t))
        elif key == 'home':
            self.tx = 0
        elif key == 'end':
            self.tx = len(t)
        elif key == 'backspace' and x > 0:
            self.title, self.tx = t[:x - 1] + t[x:], x - 1
        elif key == 'del':
            self.title = t[:x] + t[x + 1:]
        elif keys.is_text(key):
            self.title, self.tx = t[:x] + key + t[x:], x + 1
        return None

    def _body_key(self, key):
        lines, y, x = self.doc.lines, self.cy, self.cx
        if key in MOVE_KEYS:
            self._move(key)
            return None
        if key == 'backspace' and x > 0:
            lines[y] = lines[y][:x - 1] + lines[y][x:]
            self.cx -= 1
        elif key == 'backspace' and y > 0:
            self.cx = len(lines[y - 1])
            lines[y - 1] += lines.pop(y)
            self.cy -= 1
        elif key == 'del' and x < len(lines[y]):
            lines[y] = lines[y][:x] + lines[y][x + 1:]
        elif key == 'del' and y < len(lines) - 1:
            lines[y] += lines.pop(y + 1)
        elif key == 'enter':
            lines.insert(y + 1, lines[y][x:])
            lines[y] = lines[y][:x]
            self.cy, self.cx = y + 1, 0
        elif keys.is_text(key):
            lines[y] = lines[y][:x] + key + lines[y][x:]
            self.cx += 1
        else:
            return None
        self.doc.changed()
        self.want = self._position()[1]
        return None

    # ---- cursor movement

    def _position(self):
        """The cursor's (row, column) within its line's screen rows."""
        starts = wrap(self.doc.lines[self.cy], self.width)
        row = max(i for i, s in enumerate(starts) if s <= self.cx)
        return row, self.cx - starts[row]

    def _row_end(self, starts, row):
        line = self.doc.lines[self.cy]
        return starts[row + 1] - 1 if row + 1 < len(starts) else len(line)

    def _move(self, key):
        lines = self.doc.lines
        row, _ = self._position()
        starts = wrap(lines[self.cy], self.width)
        if key == 'up' and self.cy == 0 and row == 0:
            self.in_title, self.tx = True, len(self.title)
            return
        if key in ('up', 'down', 'pgup', 'pgdn'):
            step = -1 if key in ('up', 'pgup') else 1
            for _ in range(self.rows if key in ('pgup', 'pgdn') else 1):
                if not self._vertical(step):
                    break
            return  # keep self.want
        if key == 'left' and self.cx > 0:
            self.cx -= 1
        elif key == 'left' and self.cy > 0:
            self.cy -= 1
            self.cx = len(lines[self.cy])
        elif key == 'right' and self.cx < len(lines[self.cy]):
            self.cx += 1
        elif key == 'right' and self.cy < len(lines) - 1:
            self.cy, self.cx = self.cy + 1, 0
        elif key == 'home':
            self.cx = starts[row]
        elif key == 'end':
            self.cx = self._row_end(starts, row)
        self.want = self._position()[1]

    def _vertical(self, step):
        """One screen row up (-1) or down (1). False when there is none."""
        lines = self.doc.lines
        row, _ = self._position()
        starts = wrap(lines[self.cy], self.width)
        if step < 0 and row == 0:
            if self.cy == 0:
                self.cx = 0
                return False
            self.cy -= 1
            starts = wrap(lines[self.cy], self.width)
            row = len(starts) - 1
        elif step > 0 and row == len(starts) - 1:
            if self.cy == len(lines) - 1:
                self.cx = len(lines[self.cy])
                return False
            self.cy, row = self.cy + 1, 0
            starts = wrap(lines[self.cy], self.width)
        else:
            row += step
        self.cx = min(starts[row] + self.want, self._row_end(starts, row))
        return True

    def _scroll(self):
        """Moves self.top so the cursor is on screen. Returns the cursor's
        screen row counted from the top of the body."""
        lines = self.doc.lines
        row, _ = self._position()
        line, top_row = self.top
        if line < len(lines):
            self.top = (line, min(top_row, len(wrap(lines[line], self.width)) - 1))
        if (self.cy, row) < self.top:
            self.top = (self.cy, row)
        line, top_row = self.top
        offset = sum(len(wrap(lines[i], self.width)) for i in range(line, self.cy)) - top_row + row
        while offset >= self.rows:
            line, top_row = self.top
            if top_row + 1 < len(wrap(lines[line], self.width)):
                self.top = (line, top_row + 1)
            else:
                self.top = (line + 1, 0)
            offset -= 1
        return offset

    # ---- drawing

    def draw(self, screen, rect, focused, alone, upright):
        """Draws the window in rect. Returns the cursor's screen cell when
        focused, otherwise None. upright: draw the cursor with a bar glyph."""
        y, x, h, w = rect
        pad = SPLIT_PADDING
        if alone and w > PAGE_WIDTH:
            style.fill(screen, y, x, h, w, style.BACKDROP)
            x, w, pad = x + (w - PAGE_WIDTH) // 2, PAGE_WIDTH, PADDING
        style.fill(screen, y, x, h, w, style.PAGE)
        left, self.width = x + pad, w - 2 * pad
        self.rows = max(h - BODY_TOP, 1)

        def put(row, col, text, attr):
            if text:
                screen.addnstr(row, col, text, x + w - col, attr)

        put(y + 1, left, 'DOCUMENT', style.LABEL)
        shift = max(0, self.tx - self.width + 1)  # a long title scrolls
        put(y + 2, left, self.title[shift:shift + self.width], style.TITLE)
        put(y + 3, left, '─' * self.width, style.LINE)

        offset = self._scroll()
        lines = self.doc.lines
        line, row = self.top
        for screen_row in range(y + BODY_TOP, y + BODY_TOP + self.rows):
            if line >= len(lines):
                break
            text = lines[line]
            starts = wrap(text, self.width)
            end = starts[row + 1] if row + 1 < len(starts) else len(text)
            level = heading_level(text)
            if level and row == 0:
                put(screen_row, left, text[:level], style.LABEL)  # the # marks
                put(screen_row, left + level, text[level:end], style.TITLE)
            else:
                put(screen_row, left, text[starts[row]:end], style.TITLE if level else style.TEXT)
            line, row = (line, row + 1) if row + 1 < len(starts) else (line + 1, 0)

        if not focused:
            return None
        if self.in_title:
            cell = (y + 2, left + self.tx - shift)
            char = self.title[self.tx:self.tx + 1] or ' '
            attr = style.TITLE
        else:
            cell = (y + BODY_TOP + offset, left + self._position()[1])
            text = lines[self.cy]
            char = text[self.cx:self.cx + 1] or ' '
            level = heading_level(text)
            attr = style.LABEL if self.cx < level else style.TITLE if level else style.TEXT
        if upright:
            barred = cursor_font.with_bar(char)
            if barred:
                screen.addstr(*cell, barred, attr)
            else:
                screen.addstr(*cell, char, attr | curses.A_REVERSE)
        return cell
