"""The editor window: a document's title above its body, drawn in pixels.

The body wraps between words and scrolls. Lines starting with '# ', '## '
or '### ' are headings, drawn bigger. A new document starts in the title,
and its body can't be reached until the title has text. With the whole
screen to itself the editor is a centred page with rounded corners; beside
other windows it fills its window. Only rows that changed are redrawn.
"""

import document
import keys
import style

MOVE_KEYS = ('left', 'right', 'up', 'down', 'home', 'end', 'pgup', 'pgdn')
LONE_HEADER = (72, 128, 168)   # label baseline, title baseline, line: below the page top
SPLIT_HEADER = (40, 90, 124)   # the same, beside other windows
BODY_GAP = 20                  # from the line under the title to the first row


def heading_level(line):
    """1, 2 or 3 for lines starting '# ', '## ' or '### '; otherwise 0."""
    marks = len(line) - len(line.lstrip('#'))
    return marks if 1 <= marks <= 3 and line[marks:marks + 1] == ' ' else 0


def row_style(line):
    """(font, colour, row height) for a line."""
    return style.ROW_STYLES[heading_level(line)]


def wrap(text, face, width):
    """Where each screen row of text starts, breaking after a space so each
    row fits width pixels. Spaces may hang past the edge."""
    starts, x, space = [0], 0.0, None
    for i, char in enumerate(text):
        advance = face.advance(char)
        if char != ' ' and x + advance > width and i > starts[-1]:
            starts.append(space + 1 if space is not None and space >= starts[-1] else i)
            x, space = face.width(text[starts[-1]:i]), None
        x += advance
        if char == ' ':
            space = i
    return starts


def index_at(text, start, end, face, x):
    """The position in text[start:end] nearest to x pixels from start."""
    pos = 0.0
    for i in range(start, end):
        advance = face.advance(text[i])
        if x < pos + advance / 2:
            return i
        pos += advance
    return end


class Editor:
    def __init__(self, doc):
        self.doc = doc
        self.title = doc.title          # the title as it is being typed
        self.in_title = not doc.title
        self.tx = len(self.title)       # cursor position in the title
        self.cy = self.cx = 0           # cursor line and position in the body
        self.want = 0.0                 # the x (pixels) Up and Down aim for
        self.top = (0, 0)               # first line and row shown
        self.width, self.body_height = 800, 480  # set when drawn
        self._frame, self._drawn = None, {}

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

    def _starts(self, line):
        text = self.doc.lines[line]
        return wrap(text, row_style(text)[0], self.width)

    def _position(self):
        """The cursor's row within its line, and its x in pixels in that row."""
        text = self.doc.lines[self.cy]
        starts = self._starts(self.cy)
        row = max(i for i, s in enumerate(starts) if s <= self.cx)
        return row, row_style(text)[0].width(text[starts[row]:self.cx])

    def _row_end(self, line, starts, row):
        return starts[row + 1] - 1 if row + 1 < len(starts) else len(self.doc.lines[line])

    def _move(self, key):
        lines = self.doc.lines
        row, _ = self._position()
        starts = self._starts(self.cy)
        if key == 'up' and self.cy == 0 and row == 0:
            self.in_title, self.tx = True, len(self.title)
            return
        if key in ('up', 'down', 'pgup', 'pgdn'):
            step = -1 if key in ('up', 'pgup') else 1
            for _ in range(max(self.body_height // 40, 1) if key in ('pgup', 'pgdn') else 1):
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
            self.cx = self._row_end(self.cy, starts, row)
        self.want = self._position()[1]

    def _vertical(self, step):
        """One screen row up (-1) or down (1). False when there is none."""
        lines = self.doc.lines
        row, _ = self._position()
        starts = self._starts(self.cy)
        if step < 0 and row == 0:
            if self.cy == 0:
                self.cx = 0
                return False
            self.cy -= 1
            starts = self._starts(self.cy)
            row = len(starts) - 1
        elif step > 0 and row == len(starts) - 1:
            if self.cy == len(lines) - 1:
                self.cx = len(lines[self.cy])
                return False
            self.cy, row = self.cy + 1, 0
            starts = self._starts(self.cy)
        else:
            row += step
        text = lines[self.cy]
        self.cx = index_at(text, starts[row], self._row_end(self.cy, starts, row),
                           row_style(text)[0], self.want)
        return True

    # ---- scrolling

    def _rows(self, line, row):
        """(line, row, starts, height) for each screen row from here on."""
        lines = self.doc.lines
        while line < len(lines):
            starts = self._starts(line)
            height = row_style(lines[line])[2]
            for r in range(min(row, len(starts) - 1), len(starts)):
                yield line, r, starts, height
            line, row = line + 1, 0

    def _scroll(self):
        """Moves self.top so the cursor's row is inside the body."""
        cursor = (self.cy, self._position()[0])
        if cursor < self.top or self.top[0] >= len(self.doc.lines):
            self.top = cursor
        used = 0
        for line, row, _, height in self._rows(*self.top):
            used += height
            if (line, row) >= cursor:
                break
        while used > self.body_height and self.top < cursor:
            line, row, starts, height = next(self._rows(*self.top))
            used -= height
            self.top = (line, row + 1) if row + 1 < len(starts) else (line + 1, 0)

    # ---- drawing

    def draw(self, canvas, rect, focused, alone, full=False):
        """Draws the window in rect = (x, y, width, height). Unless full, or
        the window moved, only what changed since the last call is redrawn."""
        rx, ry, rw, rh = rect
        lone = alone and rw > style.PAGE_WIDTH
        if lone:
            px, py, pw, ph = (rx + (rw - style.PAGE_WIDTH) // 2, ry + style.PAGE_TOP,
                              style.PAGE_WIDTH, rh - style.PAGE_TOP)
            pad, header, inner = style.PADDING, LONE_HEADER, 1
        else:
            px, py, pw, ph = rect
            pad, header, inner = style.SPLIT_PADDING, SPLIT_HEADER, 0
        left, self.width = px + pad, pw - 2 * pad
        body_top = py + header[2] + BODY_GAP
        self.body_height = py + ph - 16 - body_top

        if full or self._frame != (rect, lone):
            self._frame, self._drawn = (rect, lone), {}
            if lone:
                canvas.fill(rx, ry, rw, rh, style.BACKDROP)
                canvas.rounded(px, py, pw, ph, style.RADIUS, style.BORDER, style.BACKDROP)
                canvas.rounded(px + 1, py + 1, pw - 2, ph - 2, style.RADIUS - 1, style.PAGE, style.BORDER)
            else:
                canvas.fill(rx, ry, rw, rh, style.PAGE)
            canvas.text(style.LABEL_FACE, left, py + header[0], 'DOCUMENT', style.LABEL, style.PAGE)
            canvas.fill(px + inner, py + header[2], pw - 2 * inner, 1, style.LINE)

        self._draw_title(canvas, left, py + header[1], focused and self.in_title)
        self._scroll()
        cursor = None
        if focused and not self.in_title:
            row, x = self._position()
            cursor = (self.cy, row, x)
        y, shown = body_top, set()
        for line, row, starts, height in self._rows(*self.top):
            if y + height > body_top + self.body_height:
                break
            text = self.doc.lines[line]
            end = starts[row + 1] if row + 1 < len(starts) else len(text)
            level = heading_level(text)
            item = (text[starts[row]:end], level, row == 0, height,
                    cursor[2] if cursor and cursor[:2] == (line, row) else None)
            if self._drawn.get(y) != item:
                self._drawn[y] = item
                self._draw_row(canvas, left, y, item)
            shown.add(y)
            y += height
        for old in [k for k in self._drawn if isinstance(k, int) and k not in shown]:
            if old >= y:
                canvas.fill(left - 8, old, self.width + 16, self._drawn[old][3], style.PAGE)
            del self._drawn[old]

    def _draw_title(self, canvas, left, baseline, with_cursor):
        face = style.TITLE_FACE
        item = (self.title, self.tx if with_cursor else None, self.width)
        if self._drawn.get('title') == item:
            return
        self._drawn['title'] = item
        canvas.fill(left - 8, baseline - face.ascent - 6, self.width + 16,
                    face.ascent + face.descent + 12, style.PAGE)
        right = left + self.width + 8
        if self.title:
            canvas.text(face, left - 2, baseline, self.title, style.TITLE, style.PAGE, right)
        else:
            canvas.text(face, left - 2, baseline, 'Untitled', style.LINE, style.PAGE, right)
        if with_cursor:
            x = left - 2 + face.width(self.title[:self.tx])
            self._cursor(canvas, min(x, right - 4), baseline, face)

    def _draw_row(self, canvas, left, y, item):
        segment, level, first, height, cursor_x = item
        face, colour, _ = style.ROW_STYLES[level]
        canvas.fill(left - 8, y, self.width + 16, height, style.PAGE)
        baseline = y + (height + face.ascent - face.descent) // 2
        right, x = left + self.width + 8, left
        if level and first:  # a heading's # marks, dimmed
            x = canvas.text(face, x, baseline, segment[:level + 1], style.LABEL, style.PAGE, right)
            segment = segment[level + 1:]
        canvas.text(face, x, baseline, segment, colour, style.PAGE, right)
        if cursor_x is not None:
            self._cursor(canvas, min(left + cursor_x, right - 4), baseline, face)

    @staticmethod
    def _cursor(canvas, x, baseline, face):
        canvas.fill(round(x), baseline - face.ascent + 2, style.CURSOR_WIDTH,
                    face.ascent + face.descent - 2, style.TITLE)
