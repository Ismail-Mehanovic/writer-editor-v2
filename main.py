#!/usr/bin/env python3
"""Stage 1: minimal curses editor. Type, backspace, Ctrl+Q to quit."""

import curses
import locale
import traceback

QUIT_KEY = '\x11'  # Ctrl+Q
BACKSPACE_KEYS = (curses.KEY_BACKSPACE, '\x7f', '\x08')


def redraw_line(screen, lines, y):
    screen.move(y, 0)
    screen.clrtoeol()
    screen.addstr(y, 0, lines[y])


def main(screen):
    curses.curs_set(1)
    lines = ['']
    cy, cx = 0, 0

    while True:
        screen.move(cy, cx)
        screen.refresh()
        key = screen.get_wch()

        if key == QUIT_KEY:
            return

        elif key in BACKSPACE_KEYS:
            if cx > 0:
                line = lines[cy]
                lines[cy] = line[:cx - 1] + line[cx:]
                cx -= 1
                redraw_line(screen, lines, cy)
            elif cy > 0:
                cx = len(lines[cy - 1])
                lines[cy - 1] += lines[cy]
                del lines[cy]
                cy -= 1
                screen.clear()
                for row, text in enumerate(lines):
                    screen.addstr(row, 0, text)

        elif key in ('\n', '\r', curses.KEY_ENTER):
            line = lines[cy]
            lines[cy] = line[:cx]
            lines.insert(cy + 1, line[cx:])
            cy += 1
            cx = 0
            screen.clear()
            for row, text in enumerate(lines):
                screen.addstr(row, 0, text)

        elif isinstance(key, str) and key.isprintable():
            line = lines[cy]
            lines[cy] = line[:cx] + key + line[cx:]
            cx += 1
            redraw_line(screen, lines, cy)


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    try:
        curses.wrapper(main)
    except Exception:
        traceback.print_exc()
