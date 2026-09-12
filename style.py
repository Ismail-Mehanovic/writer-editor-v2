"""Colours and the navy look.

The Linux console has 16 colours, but a program may redefine what they
look like (the palette). This redefines a few to match the design: a dark
backdrop, a navy page, a muted label colour and bright white titles. The
attribute names below (PAGE, TITLE, ...) are set by init().
"""

import curses
import sys

# Console colour slot -> the colour it shows. Slots 8-15 are the bright
# versions of 0-7, which curses reaches through A_BOLD.
PALETTE = {
    0: '070b16',   # backdrop around the page
    4: '131b2e',   # the page
    5: '22304d',   # the selected file in a file list
    6: '8b9bb4',   # labels ("DOCUMENT", "FILES") and the status line
    7: 'd8dee9',   # body text
    8: '2d3a57',   # lines: dividers, window separators
    14: '7aa2f7',  # the frame around the selected window
    15: 'ffffff',  # titles and headings
}

BACKDROP = PAGE = TEXT = LABEL = LINE = TITLE = SELECTED = FRAME = STATUS = 0


def set_palette():
    sys.stdout.write(''.join(f'\033]P{n:X}{rgb}' for n, rgb in PALETTE.items()))
    sys.stdout.flush()


def reset_palette():
    sys.stdout.write('\033]R')
    sys.stdout.flush()


def init():
    """Sets up the colour pairs. Without colours everything stays plain."""
    global BACKDROP, PAGE, TEXT, LABEL, LINE, TITLE, SELECTED, FRAME, STATUS
    if not curses.has_colors():
        return
    curses.start_color()

    def pair(number, fg, bg, extra=0):
        curses.init_pair(number, fg, bg)
        return curses.color_pair(number) | extra

    BACKDROP = pair(1, 7, 0)
    STATUS = pair(2, 6, 0)
    PAGE = TEXT = pair(3, 7, 4)
    LABEL = pair(4, 6, 4)
    LINE = pair(5, 0, 4, curses.A_BOLD)         # slot 8
    TITLE = pair(6, 7, 4, curses.A_BOLD)        # slot 15
    SELECTED = pair(7, 7, 5, curses.A_BOLD)
    FRAME = pair(8, 6, 4, curses.A_BOLD)        # slot 14


def fill(screen, y, x, height, width, attr):
    """Paints a rectangle in attr's background colour."""
    for row in range(y, y + height):
        try:
            screen.addstr(row, x, ' ' * width, attr)
        except curses.error:
            pass  # the very last cell of the screen can't be written
