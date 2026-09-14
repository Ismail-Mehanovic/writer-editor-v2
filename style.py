"""The look: colours, fonts and sizes, taken from the design screenshots.

Everything is drawn in pixels (render.py) with the fonts in fonts/. The
numbers here are the full size in the modern typeface; sizes(zoom) gives
them all in the typeface chosen in the settings, scaled to one window's
zoom (Ctrl+plus, Ctrl+minus).
"""

import os

from render import Face

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')

# Neutral greys, all a long way down from white: blue light at night is
# what makes a screen hurt to look at, so nothing here is tinted, and only
# the text itself is bright. Each grey is a multiple of 8, which is what
# the screen's 16-bit colour can show without a tint creeping back in.
BACKDROP = (8, 8, 8)         # around the page
PAGE = (24, 24, 24)          # the page, and every window beside others
RAISED = (32, 32, 32)        # a card over a window (the delete question)
BORDER = (40, 40, 40)        # the page's edge
MARKER = (120, 120, 120)     # the outline round the row the keys act on
LINE = (56, 56, 56)          # the line under a title, lines between windows
SELECTION = (72, 72, 72)     # behind selected text
LABEL = (120, 120, 120)      # "DOCUMENT", the status line, heading marks
TEXT_DIM = (136, 136, 136)   # body text in a window that isn't in use
ACCENT = (144, 144, 144)     # the select-mode frame
TITLE_DIM = (176, 176, 176)  # titles and headings in a window not in use
TEXT = (208, 208, 208)       # body text
TITLE = (255, 255, 255)      # titles, headings, the cursor
DANGER = (168, 56, 56)       # the Delete button, when chosen

PAGE_WIDTH = 960             # a lone document is a page this wide, centred
PAGE_TOP = 28                # gap above the page
RADIUS = 12                  # the page's rounded corners
PADDING = 72                 # page edge to text, on the lone page
SPLIT_PADDING = 32           # window edge to text, beside other windows
STATUS_HEIGHT = 32           # the status line at the bottom of the screen
CURSOR_WIDTH = 2


def _face(name, size, spacing=0.0):
    return Face(os.path.join(FONTS, name), size, spacing)


STATUS_FACE = _face('Selawik-Regular.ttf', 16)  # the bottom line: never changes

# The typefaces the settings window offers: the modern one from the design,
# a classical serif, and a monospace whose square letters suit the panel's
# coarse pixels. (shown as, regular, semibold, bold, size tweak: the mono
# one is taller and much wider, so it is drawn a little smaller.)
FAMILIES = {
    'modern': ('Modern', 'Selawik-Regular.ttf', 'Selawik-Semibold.ttf',
               'Selawik-Bold.ttf', 1.0),
    'classic': ('Classic', 'PT_Serif-Web-Regular.ttf', 'PT_Serif-Web-Bold.ttf',
                'PT_Serif-Web-Bold.ttf', 1.0),
    'mono': ('Mono', 'JetBrainsMono-Regular.ttf', 'JetBrainsMono-SemiBold.ttf',
             'JetBrainsMono-Bold.ttf', 0.87),
}
FONT_ORDER = ('modern', 'classic', 'mono')
FONT_DEFAULT = 'modern'
FONT = FONT_DEFAULT  # the one in use everywhere; the settings window sets it

LABEL_SIZE, LABEL_SPACING = 15, 1.6  # "DOCUMENT", "SETTINGS"
LABEL_MIN = 10               # smaller than this the label turns to mush
TITLE_SIZE, BODY_SIZE, LIST_SIZE = 44, 24, 22
BODY_ROW = 38                # the height of a plain line of text
HEADINGS = {                 # '#', '##', '###': weight, text size, row height
    1: ('bold', 34, 54),
    2: ('bold', 29, 48),
    3: ('semibold', 26, 42),
}

# Zoom. Every window has its own (Ctrl+plus, Ctrl+minus): the full size
# above is a lot on a 10 inch panel, so a window starts at ZOOM_DEFAULT.
ZOOM_STEPS = (0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 1.0)
ZOOM_DEFAULT = 0.5


def use_font(name):
    """Draws everything in this typeface from now on. It is one choice for
    the whole editor, so it lives here and not in each window."""
    global FONT
    FONT = name if name in FAMILIES else FONT_DEFAULT


def zoom_step(zoom, direction):
    """The next zoom bigger (direction 1) or smaller (-1); at the ends, the
    same one back."""
    i = ZOOM_STEPS.index(zoom) if zoom in ZOOM_STEPS else ZOOM_STEPS.index(ZOOM_DEFAULT)
    return ZOOM_STEPS[min(max(i + direction, 0), len(ZOOM_STEPS) - 1)]


class Sizes:
    """Every measurement in one typeface at one zoom: the fonts, the page,
    the gaps around the text. Made once for each pair and then kept for good
    (see sizes), because the remembered line wraps and letter pictures are
    keyed on the font objects in here."""

    def __init__(self, zoom, font):
        self.zoom, self.font = zoom, font
        _, regular, semibold, bold, tweak = FAMILIES[font]
        self.files = {'regular': regular, 'semibold': semibold, 'bold': bold}
        self.scale = zoom * tweak  # letters follow the typeface's tweak, gaps don't
        self.PAGE_WIDTH = self.px(PAGE_WIDTH)
        self.PAGE_TOP = self.px(PAGE_TOP)
        self.RADIUS = self.px(RADIUS)
        self.PADDING = self.px(PADDING)
        self.SPLIT_PADDING = self.px(SPLIT_PADDING)
        self.LABEL_FACE = self.face('semibold', max(LABEL_SIZE * self.scale, LABEL_MIN),
                                    LABEL_SPACING * self.scale)
        self.TITLE_FACE = self.face('bold', TITLE_SIZE * self.scale)
        self.BODY_FACE = self.face('regular', BODY_SIZE * self.scale)
        self.LIST_FACE = self.face('regular', LIST_SIZE * self.scale)
        self.ROW_STYLES = {0: (self.BODY_FACE, TEXT, self.px(BODY_ROW))}
        for level, (weight, size, height) in HEADINGS.items():
            self.ROW_STYLES[level] = (self.face(weight, size * self.scale), TITLE, self.px(height))

    def face(self, weight, size, spacing=0.0):
        return _face(self.files[weight], size, spacing)

    def px(self, length):
        """A length from the full-size design, at this zoom (never nothing)."""
        return max(round(length * self.zoom), 1)


_sizes = {}


def sizes(zoom, font=None):
    """The Sizes for zoom in the typeface in use, or in a named one: the
    same object every time it is asked for."""
    key = (zoom, font or FONT)
    if key not in _sizes:
        _sizes[key] = Sizes(*key)
    return _sizes[key]
