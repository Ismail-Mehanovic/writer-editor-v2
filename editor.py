"""The editor window: a document's title above its body, drawn in pixels.

The body wraps between words. Lines starting with '# ', '## ' or '### '
are headings, drawn bigger; their # marks show only on the cursor's line. Ctrl+A or Shift with the arrows selects text;
Ctrl+C, Ctrl+X and Ctrl+V copy, cut and paste, and typing replaces a
selection. A new document starts in the title, and its body can't be
reached until the title has text; a title too long for its line slides
sideways as it is typed. The document scrolls as one piece: once the
writing reaches the bottom, the title and the page's top edge move up out
of sight as well. With the whole screen to itself the editor is a centred
page with rounded corners; beside other windows it fills its window, and
is drawn dimmer while another window is in use. Ctrl+plus and Ctrl+minus
make this window's text bigger or smaller (self.zoom, style.sizes). Only
rows that changed are redrawn, and scrolling down moves what is already
drawn.
"""

import document
import keys
import style

MOVE_KEYS = ('left', 'right', 'up', 'down', 'home', 'end', 'pgup', 'pgdn')
LONE_HEADER = (72, 128, 168)   # label baseline, title baseline, line: below the page top
SPLIT_HEADER = (40, 90, 124)   # the same, beside other windows
BODY_GAP = 20                  # from the line under the title to the first row
MARGIN = 24                    # the cursor stays this far inside the window's top and bottom

_wrapped = {}  # wrap() results, so scrolling needn't measure every line again


def heading_level(line):
    """1, 2 or 3 for lines starting '# ', '## ' or '### '; otherwise 0."""
    marks = len(line) - len(line.lstrip('#'))
    return marks if 1 <= marks <= 3 and line[marks:marks + 1] == ' ' else 0


def row_style(sizes, line):
    """(font, colour, row height) for a line, at one window's zoom."""
    return sizes.ROW_STYLES[heading_level(line)]


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


def wrapped(text, face, width):
    """wrap(), remembered."""
    key = (text, id(face), width)
    if key not in _wrapped:
        if len(_wrapped) > 20000:
            _wrapped.clear()
        _wrapped[key] = wrap(text, face, width)
    return _wrapped[key]


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
    clipboard = ''  # copied text, shared by every editor window

    def __init__(self, doc):
        self.doc = doc
        self.zoom = style.ZOOM_DEFAULT  # this window's text size
        self.title = doc.title          # the title as it is being typed
        self.in_title = not doc.title
        self.tx = len(self.title)       # cursor position in the title
        self.cy = self.cx = 0           # cursor line and position in the body
        self.want = 0.0                 # the x (pixels) Up and Down aim for
        self.scroll = 0                 # how many pixels of the document are above the window
        self.title_shift = 0.0          # how far a long title has slid left
        self.width, self.body_height = 800, 480  # set when drawn
        self._frame, self._drawn = None, {}
        self.cursor_on = True           # off for half of every blink
        self.anchor = None              # (line, column) where a selection began
        self._words = (-1, 0)           # (document version, word count)
        self._scrolled = 0              # self.scroll when last drawn

    def words(self):
        """The word count, worked out again only after the text changed."""
        if self._words[0] != self.doc.version:
            self._words = (self.doc.version, sum(len(line.split()) for line in self.doc.lines))
        return self._words[1]

    @property
    def sizes(self):
        """The fonts and measurements at this window's zoom."""
        return style.sizes(self.zoom)

    # ---- keys

    def handle(self, key):
        """Acts on one key. Returns a message for the status line, or None."""
        return self._title_key(key) if self.in_title else self._body_key(key)

    def _title_key(self, key):
        if key.startswith('shift-'):
            key = key[6:]  # nothing is selected in the title
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
        if key == 'ctrl-a':
            self.anchor = (0, 0)
            self.cy, self.cx = len(self.doc.lines) - 1, len(self.doc.lines[-1])
            return None
        if key.startswith('shift-') and key[6:] in MOVE_KEYS:
            if self.anchor is None:
                self.anchor = (self.cy, self.cx)
            self._move(key[6:], extend=True)
            return None
        span = self.selection()
        if key in MOVE_KEYS:
            self.anchor = None
            if span and key in ('left', 'right'):  # to the start or end of the selection
                self.cy, self.cx = span[0] if key == 'left' else span[1]
                self.want = self._position()[1]
            else:
                self._move(key)
            return None
        if key in ('ctrl-c', 'ctrl-x'):
            if not span:
                return 'Select some text first: Shift+arrows, or Ctrl+A for all of it.'
            Editor.clipboard = self._text(span)
            if key == 'ctrl-c':
                return 'Copied.'
            self._remove(span)
        elif key == 'ctrl-v':
            if not Editor.clipboard:
                return 'Nothing has been copied yet.'
            if span:
                self._remove(span)
            self._insert(Editor.clipboard)
        elif span and (key in ('backspace', 'del', 'enter') or keys.is_text(key)):
            self._remove(span)  # Backspace and Del remove it; anything typed replaces it
            if key not in ('backspace', 'del'):
                return self._edit(key)
        else:
            self.anchor = None
            return self._edit(key)
        self.doc.changed()
        self.want = self._position()[1]
        return None

    def _edit(self, key):
        """Typing, Enter, Backspace and Del with nothing selected."""
        lines, y, x = self.doc.lines, self.cy, self.cx
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

    # ---- selection

    def selection(self):
        """(start, end) of the selected text as (line, column) pairs, or None."""
        if self.anchor is None or self.anchor == (self.cy, self.cx):
            return None
        return tuple(sorted([self.anchor, (self.cy, self.cx)]))

    def _text(self, span):
        (first, start), (last, end) = span
        lines = self.doc.lines
        if first == last:
            return lines[first][start:end]
        return '\n'.join([lines[first][start:]] + lines[first + 1:last] + [lines[last][:end]])

    def _remove(self, span):
        (first, start), (last, end) = span
        lines = self.doc.lines
        lines[first:last + 1] = [lines[first][:start] + lines[last][end:]]
        self.cy, self.cx, self.anchor = first, start, None

    def _insert(self, text):
        """Puts text (perhaps several lines) at the cursor."""
        parts = text.split('\n')
        line = self.doc.lines[self.cy]
        before, after = line[:self.cx], line[self.cx:]
        parts[0] = before + parts[0]
        parts[-1] += after  # the same line as parts[0] when text has no line break
        self.doc.lines[self.cy:self.cy + 1] = parts
        self.cy += len(parts) - 1
        self.cx = len(parts[-1]) - len(after)

    def _row_selection(self, span, line, starts, row, end):
        """What is selected in one screen row: (from, to, line break too) as
        positions in the row, or None."""
        (first, start), (last, stop) = span
        if not first <= line <= last:
            return None
        length = len(self.doc.lines[line])
        a = max(start if line == first else 0, starts[row])
        b = min(stop if line == last else length, end)
        line_break = line < last and end == length
        if a >= b and not line_break:
            return None
        return (a - starts[row], max(a, b) - starts[row], line_break)

    # ---- cursor movement

    def _starts(self, line):
        text = self.doc.lines[line]
        return wrapped(text, row_style(self.sizes, text)[0], self.width)

    def _position(self):
        """The cursor's row within its line, and its x in pixels in that row."""
        text = self.doc.lines[self.cy]
        starts = self._starts(self.cy)
        row = max(i for i, s in enumerate(starts) if s <= self.cx)
        return row, row_style(self.sizes, text)[0].width(text[starts[row]:self.cx])

    def _row_end(self, line, starts, row):
        return starts[row + 1] - 1 if row + 1 < len(starts) else len(self.doc.lines[line])

    def _move(self, key, extend=False):
        lines = self.doc.lines
        row, _ = self._position()
        starts = self._starts(self.cy)
        if key == 'up' and self.cy == 0 and row == 0 and not extend:
            self.in_title, self.tx, self.anchor = True, len(self.title), None
            return
        if key in ('up', 'down', 'pgup', 'pgdn'):
            step = -1 if key in ('up', 'pgup') else 1
            page = max(self.body_height // self.sizes.ROW_STYLES[0][2], 1)  # rows in a windowful
            for _ in range(page if key in ('pgup', 'pgdn') else 1):
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
                           row_style(self.sizes, text)[0], self.want)
        return True

    # ---- scrolling

    def _cursor_y(self, body_top):
        """Where the cursor's row starts, in pixels from the document's top,
        and how tall it is."""
        lines, sizes = self.doc.lines, self.sizes
        y = body_top
        for line in range(self.cy):
            y += len(self._starts(line)) * row_style(sizes, lines[line])[2]
        height = row_style(sizes, lines[self.cy])[2]
        return y + self._position()[0] * height, height

    def _follow_cursor(self, view, body_top):
        """Scrolls so the cursor is inside the window (view pixels tall). The
        whole top, title included, comes back once there is room for it."""
        if self.in_title:
            self.scroll = 0
            return
        margin = self.sizes.px(MARGIN)
        top, height = self._cursor_y(body_top)
        if top + height > self.scroll + view - margin:
            self.scroll = top + height - view + margin
        elif top < self.scroll + margin:
            self.scroll = 0 if top + height <= view - margin else top - margin

    # ---- drawing

    def draw(self, canvas, rect, focused, alone, full=False, active=True):
        """Draws the window in rect = (x, y, width, height). focused: show the
        cursor; active: the window in use (others are drawn dimmer). Unless
        full or the window moved, only what changed is redrawn."""
        rx, ry, rw, rh = rect
        s = self.sizes
        lone = alone and rw > s.PAGE_WIDTH
        if lone:
            px, pw = rx + (rw - s.PAGE_WIDTH) // 2, s.PAGE_WIDTH
            pad, header, page_top, edge = s.PADDING, LONE_HEADER, s.PAGE_TOP, 1
        else:
            px, pw = rx, rw
            pad, header, page_top, edge = s.SPLIT_PADDING, SPLIT_HEADER, 0, 0
        header = tuple(s.px(v) for v in header)
        left, self.width = px + pad, pw - 2 * pad
        body_top = page_top + header[2] + s.px(BODY_GAP)  # from the document's top
        self.body_height = rh - 2 * s.px(MARGIN)
        self._follow_cursor(rh, body_top)
        top = ry - self.scroll  # where the document's top is on the screen
        dim = not (active or alone)
        frame, moved = (rect, lone, dim, self.zoom), self.scroll - self._scrolled

        canvas.clip(rect)
        if not full and self._frame == frame and 0 < moved < rh // 2:
            self._shift(canvas, rect, edge, (px, pw) if lone else None, moved)
        elif full or self._frame != frame or moved:
            self._frame, self._drawn = frame, {}
            if lone:
                canvas.fill(rx, ry, rw, rh, style.BACKDROP)
                page_y = top + page_top
                canvas.rounded(px, page_y, pw, ry + rh - page_y, s.RADIUS, style.BORDER, style.BACKDROP)
                canvas.rounded(px + 1, page_y + 1, pw - 2, ry + rh - page_y - 2, s.RADIUS - 1,
                               style.PAGE, style.BORDER)
            else:
                canvas.fill(rx, ry, rw, rh, style.PAGE)
            canvas.text(s.LABEL_FACE, left, top + page_top + header[0], 'DOCUMENT', style.LABEL, style.PAGE)
            canvas.fill(px + edge, top + page_top + header[2], pw - 2 * edge, 1, style.LINE)
        self._scrolled = self.scroll
        canvas.clip((rx, ry, rw, rh - edge))  # the lone page's bottom edge stays put
        try:
            self._draw_title(canvas, left, top + page_top + header[1],
                             focused and self.in_title and self.cursor_on, dim)
            self._draw_rows(canvas, left, top + body_top, ry, ry + rh - edge, focused, dim)
        finally:
            canvas.clip(None)

    def _shift(self, canvas, rect, edge, page, moved):
        """Scrolling down: moves what is on screen up by `moved` pixels and
        clears the strip that opens at the bottom, so only rows coming into
        view need drawing. page: the lone page's (x, width); its rounded
        bottom corners stay where they are."""
        rx, ry, rw, rh = rect
        radius = self.sizes.RADIUS
        bottom = ry + rh - edge
        limit = bottom - radius if page else bottom  # moved part ends here
        canvas.shift(rx, ry, rw, limit - ry, moved)
        drawn = {}
        for key, item in self._drawn.items():
            if key == 'title':
                drawn[key] = item[:3] + (item[3] - moved,) + item[4:]
            elif key + item[3] <= limit and key - moved + item[3] > ry:
                drawn[key - moved] = item  # was whole before, and still shows
        self._drawn = drawn
        if page:
            canvas.fill(page[0] + radius, limit - moved, page[1] - 2 * radius,
                        bottom - limit + moved, style.PAGE)
        else:
            canvas.fill(rx, limit - moved, rw, moved, style.PAGE)

    def _draw_title(self, canvas, left, baseline, with_cursor, dim):
        s = self.sizes
        face, keep = s.TITLE_FACE, s.px(12)  # keep: the cursor stays this far from the edge
        slack = s.px(6)  # cleared around the title; more would rub out the label above
        room = self.width + 4
        cursor_x = face.width(self.title[:self.tx])
        if not self.in_title or face.width(self.title) <= room:
            self.title_shift = 0.0
        elif cursor_x - self.title_shift > room - keep:  # slide left to keep the cursor in sight
            self.title_shift = cursor_x - room + keep
        elif cursor_x < self.title_shift:
            self.title_shift = max(0.0, cursor_x - s.px(60))
        item = (self.title, self.tx if with_cursor else None, self.width, baseline, self.title_shift, dim)
        if self._drawn.get('title') == item:
            return
        self._drawn['title'] = item
        canvas.fill(left - 8, baseline - face.ascent - slack, self.width + 16,
                    face.ascent + face.descent + 2 * slack, style.PAGE)
        start, end = left - 2, left + self.width + 6
        text, colour = ((self.title, style.TITLE_DIM if dim else style.TITLE) if self.title
                        else ('Untitled', style.LINE))
        canvas.text(face, start - self.title_shift, baseline, text, colour, style.PAGE, end, start)
        if with_cursor:
            self._cursor(canvas, start + cursor_x - self.title_shift, baseline, face)

    def _draw_rows(self, canvas, left, first_y, view_top, view_bottom, focused, dim):
        """The body rows that are on screen; each is redrawn only if it changed."""
        lines, span, sizes = self.doc.lines, self.selection(), self.sizes
        cursor = None
        if focused and not self.in_title and self.cursor_on:
            cursor = (self.cy,) + self._position()
        y, shown = first_y, set()
        for line, text in enumerate(lines):
            starts = self._starts(line)
            level = heading_level(text)
            height = sizes.ROW_STYLES[level][2]
            if y + height * len(starts) <= view_top:  # the whole line is above the window
                y += height * len(starts)
                continue
            if y >= view_bottom:
                break
            for row, start in enumerate(starts):
                if y + height > view_top and y < view_bottom:
                    end = starts[row + 1] if row + 1 < len(starts) else len(text)
                    item = (text[start:end], level, row == 0, height,
                            cursor[2] if cursor and cursor[:2] == (line, row) else None,
                            self._row_selection(span, line, starts, row, end) if span else None,
                            focused and line == self.cy, dim)
                    if self._drawn.get(y) != item:
                        self._drawn[y] = item
                        self._draw_row(canvas, left, y, item)
                    shown.add(y)
                y += height
        for old in [k for k in self._drawn if isinstance(k, int) and k not in shown]:
            if old >= y:
                canvas.fill(left - 8, old, self.width + 16, self._drawn[old][3], style.PAGE)
            del self._drawn[old]

    def _draw_row(self, canvas, left, y, item):
        segment, level, first, height, cursor_x, selected, show_marks, dim = item
        s = self.sizes
        face, colour, _ = s.ROW_STYLES[level]
        inset = s.px(4)  # the selection's background stops this far short of the row
        if dim:
            colour = style.TITLE_DIM if level else style.TEXT_DIM
        canvas.fill(left - 8, y, self.width + 16, height, style.PAGE)
        baseline = y + (height + face.ascent - face.descent) // 2
        right = left + self.width + 8
        marks = level + 1 if level and first else 0  # a heading's # marks: dim, or hidden
        a, b, line_break = selected or (0, 0, False)
        x, i = float(left), 0 if show_marks else marks
        while i < len(segment):  # runs of letters that share a colour and background
            chosen = a <= i < b
            j = i + 1
            while j < len(segment) and (a <= j < b) == chosen and (j < marks) == (i < marks):
                j += 1
            run, bg = segment[i:j], style.SELECTION if chosen else style.PAGE
            if chosen:
                canvas.fill(round(x), y + inset, round(face.width(run)) + 1, height - 2 * inset, bg)
            x = canvas.text(face, x, baseline, run, style.LABEL if i < marks else colour, bg, right)
            i = j
        if line_break:  # the selection goes on past the end of this line
            canvas.fill(round(x), y + inset, s.px(8), height - 2 * inset, style.SELECTION)
        if cursor_x is not None:
            self._cursor(canvas, min(left + cursor_x, right - 4), baseline, face)

    @staticmethod
    def _cursor(canvas, x, baseline, face):
        canvas.fill(round(x), baseline - face.ascent + 2, style.CURSOR_WIDTH,
                    face.ascent + face.descent - 2, style.TITLE)
