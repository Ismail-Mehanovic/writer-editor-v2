"""The screen as a tree of windows.

Every split cuts one window in half, side by side or one above the other,
with a one-cell line between the halves. The leaves of the tree are the
windows themselves (editors and file lists); the layout only knows where
they are, never what is in them.
"""

MIN_WIDTH, MIN_HEIGHT = 16, 6  # a split that would go smaller is refused


class Split:
    def __init__(self, side_by_side, first, second):
        self.side_by_side = side_by_side
        self.first, self.second = first, second


def _replace(node, old, new):
    if node is old:
        return new
    if isinstance(node, Split):
        node.first = _replace(node.first, old, new)
        node.second = _replace(node.second, old, new)
    return node


def _parent(node, child):
    if not isinstance(node, Split):
        return None
    if child is node.first or child is node.second:
        return node
    return _parent(node.first, child) or _parent(node.second, child)


def _windows(node):
    if isinstance(node, Split):
        return _windows(node.first) + _windows(node.second)
    return [node]


class Layout:
    def __init__(self, window):
        self.root = window
        self.focus = window

    def windows(self):
        return _windows(self.root)

    def place(self, y, x, height, width):
        """({window: (y, x, height, width)}, [separator lines]). A line is
        ('|', y, x, length) or ('-', y, x, length)."""
        rects, lines = {}, []

        def walk(node, y, x, h, w):
            if not isinstance(node, Split):
                rects[node] = (y, x, h, w)
            elif node.side_by_side:
                left = (w - 1) // 2
                lines.append(('|', y, x + left, h))
                walk(node.first, y, x, h, left)
                walk(node.second, y, x + left + 1, h, w - left - 1)
            else:
                top = (h - 1) // 2
                lines.append(('-', y + top, x, w))
                walk(node.first, y, x, top, w)
                walk(node.second, y + top + 1, x, h - top - 1, w)

        walk(self.root, y, x, height, width)
        return rects, lines

    def split(self, window, direction, focus_rect):
        """Puts window beside the focused one (direction: 'left', 'right',
        'up' or 'down') and focuses it. False if it wouldn't fit."""
        side_by_side = direction in ('left', 'right')
        _, _, h, w = focus_rect
        if (side_by_side and (w - 1) // 2 < MIN_WIDTH
                or not side_by_side and (h - 1) // 2 < MIN_HEIGHT):
            return False
        first, second = ((window, self.focus) if direction in ('left', 'up')
                         else (self.focus, window))
        self.root = _replace(self.root, self.focus, Split(side_by_side, first, second))
        self.focus = window
        return True

    def close(self, window):
        """Removes window; its neighbour in the split takes the space and
        the focus. False for the last window, which can't be closed."""
        parent = _parent(self.root, window)
        if parent is None:
            return False
        sibling = parent.second if window is parent.first else parent.first
        self.root = _replace(self.root, parent, sibling)
        self.focus = _windows(sibling)[0]
        return True

    def swap(self, old, new):
        """Puts new where old was (a file list becoming an editor)."""
        self.root = _replace(self.root, old, new)
        if self.focus is old:
            self.focus = new

    def neighbour(self, direction, rects):
        """The window next to the focused one in direction, or None."""
        y, x, h, w = rects[self.focus]
        mid_y, mid_x = y + h // 2, x + w // 2
        best = None
        for window, (wy, wx, wh, ww) in rects.items():
            beside = wy <= mid_y < wy + wh
            above_below = wx <= mid_x < wx + ww
            if direction == 'left' and beside and wx + ww <= x:
                gap = x - (wx + ww)
            elif direction == 'right' and beside and wx >= x + w:
                gap = wx - (x + w)
            elif direction == 'up' and above_below and wy + wh <= y:
                gap = y - (wy + wh)
            elif direction == 'down' and above_below and wy >= y + h:
                gap = wy - (y + h)
            else:
                continue
            if best is None or gap < best[0]:
                best = (gap, window)
        return best[1] if best else None
