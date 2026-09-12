"""The look: colours, fonts and sizes, taken from the design screenshots.

Everything is drawn in pixels (render.py) with the Selawik font in fonts/.
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
