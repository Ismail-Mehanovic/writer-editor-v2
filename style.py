"""The look: colours, fonts and sizes, taken from the design screenshots.

Everything is drawn in pixels (render.py) with the Selawik font in fonts/.
The numbers here are the full size; each window is drawn at its own zoom
(Ctrl+plus, Ctrl+minus), and sizes(zoom) gives them all scaled to it.
"""

import os

from render import Face

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')

BACKDROP = (7, 11, 22)       # around the page
PAGE = (19, 27, 46)          # the page, and every window beside others
BORDER = (34, 44, 68)        # the page's edge
LINE = (45, 58, 87)          # the line under a title, lines between windows
LABEL = (139, 155, 180)      # "DOCUMENT", the status line, heading marks
TEXT = (216, 222, 233)       # body text
TITLE = (255, 255, 255)      # titles, headings, the cursor
TEXT_DIM = (150, 158, 174)   # body text in a window that isn't in use
TITLE_DIM = (196, 202, 214)  # titles and headings there
SELECTED = (34, 48, 77)      # the chosen document in a file list
ACCENT = (122, 162, 247)     # the select-mode frame, "New folder"
RAISED = (26, 37, 62)        # a card over a window (the delete question)
SELECTION = (44, 70, 118)    # behind selected text
DANGER = (196, 64, 76)       # the Delete button, when chosen

PAGE_WIDTH = 960             # a lone document is a page this wide, centred
PAGE_TOP = 28                # gap above the page
RADIUS = 12                  # the page's rounded corners
PADDING = 72                 # page edge to text, on the lone page
SPLIT_PADDING = 32           # window edge to text, beside other windows
STATUS_HEIGHT = 32           # the status line at the bottom of the screen
CURSOR_WIDTH = 2


def _face(name, size, spacing=0.0):
    return Face(os.path.join(FONTS, name), size, spacing)


LABEL_FACE = _face('Selawik-Semibold.ttf', 15, spacing=1.6)
TITLE_FACE = _face('Selawik-Bold.ttf', 44)
BODY_FACE = _face('Selawik-Regular.ttf', 24)
LIST_FACE = _face('Selawik-Regular.ttf', 22)
STATUS_FACE = _face('Selawik-Regular.ttf', 16)

# Body rows: (font, colour, row height) for plain text and # / ## / ###.
ROW_STYLES = {
    0: (BODY_FACE, TEXT, 38),
    1: (_face('Selawik-Bold.ttf', 34), TITLE, 54),
    2: (_face('Selawik-Bold.ttf', 29), TITLE, 48),
    3: (_face('Selawik-Semibold.ttf', 26), TITLE, 42),
}

# Zoom. Every window has its own (Ctrl+plus, Ctrl+minus): the full size
# above is a lot on a 10 inch panel, so a window starts at ZOOM_DEFAULT.
ZOOM_STEPS = (0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 1.0)
ZOOM_DEFAULT = 0.5
LABEL_MIN = 10  # "DOCUMENT" is small already: shrunk further it turns to mush


def zoom_step(zoom, direction):
    """The next zoom bigger (direction 1) or smaller (-1); at the ends, the
    same one back."""
    i = ZOOM_STEPS.index(zoom) if zoom in ZOOM_STEPS else ZOOM_STEPS.index(ZOOM_DEFAULT)
    return ZOOM_STEPS[min(max(i + direction, 0), len(ZOOM_STEPS) - 1)]


class Sizes:
    """Every measurement at one zoom: the fonts, the page, the gaps around
    the text. Made once per zoom and then kept for good (see sizes), because
    the remembered line wraps and letter pictures are keyed on the font
    objects in here."""

    def __init__(self, zoom):
        self.zoom = zoom
        self.PAGE_WIDTH = self.px(PAGE_WIDTH)
        self.PAGE_TOP = self.px(PAGE_TOP)
        self.RADIUS = self.px(RADIUS)
        self.PADDING = self.px(PADDING)
        self.SPLIT_PADDING = self.px(SPLIT_PADDING)
        self.LABEL_FACE = LABEL_FACE.scaled(max(zoom, LABEL_MIN / LABEL_FACE.size))
        self.TITLE_FACE = TITLE_FACE.scaled(zoom)
        self.LIST_FACE = LIST_FACE.scaled(zoom)
        self.ROW_STYLES = {level: (face.scaled(zoom), colour, self.px(height))
                           for level, (face, colour, height) in ROW_STYLES.items()}

    def px(self, length):
        """A length from the full-size design, at this zoom (never nothing)."""
        return max(round(length * self.zoom), 1)


_sizes = {}


def sizes(zoom):
    """The Sizes for zoom: the same object every time it is asked for."""
    if zoom not in _sizes:
        _sizes[zoom] = Sizes(zoom)
    return _sizes[zoom]
