#!/usr/bin/env python3
"""Shows one page drawn the new, smooth way on the real screen, to judge the
look before the editor switches to it. Any key puts the screen back.

    python3 ~/writer-editor-v2/preview.py
"""

import os
import sys
import termios
import tty

import render
from render import Canvas, Face

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
BACKDROP, PAGE, BORDER, LINE = (7, 11, 22), (19, 27, 46), (34, 44, 68), (45, 58, 87)
LABEL, TITLE, TEXT = (139, 155, 180), (255, 255, 255), (216, 222, 233)
SAMPLE = ['This is the actual document. Text wraps between words inside the page,',
          'with even margins on both sides, and the cursor is a thin upright line.',
          '',
          'Swedish letters work too: å ä ö, Å Ä Ö, and so do “quotes” – and dashes.']


def draw(c):
    label = Face(os.path.join(FONTS, 'Selawik-Semibold.ttf'), 15, spacing=1.6)
    title = Face(os.path.join(FONTS, 'Selawik-Bold.ttf'), 44)
    body = Face(os.path.join(FONTS, 'Selawik-Regular.ttf'), 24)
    small = Face(os.path.join(FONTS, 'Selawik-Regular.ttf'), 16)
    c.fill(0, 0, c.w, c.h, BACKDROP)
    x, y, w, h = 160, 28, 960, 740
    c.rounded(x, y, w, h, 12, BORDER, BACKDROP)
    c.rounded(x + 1, y + 1, w - 2, h - 2, 11, PAGE, BORDER)
    c.text(label, x + 72, y + 72, 'DOCUMENT', LABEL, PAGE)
    c.text(title, x + 70, y + 128, 'This is the title', TITLE, PAGE)
    c.fill(x + 1, y + 168, w - 2, 1, LINE)
    baseline, end = y + 226, 0
    for line in SAMPLE:
        end = c.text(body, x + 76, baseline, line, TEXT, PAGE)
        baseline += 38
    c.fill(round(end) + 2, baseline - 38 - body.ascent + 2, 2, body.ascent + body.descent - 2, TITLE)
    c.text(small, x + 4, 792, 'Preview  ·  press any key to go back', LABEL, BACKDROP)


def main():
    canvas = Canvas.framebuffer()
    before = bytes(canvas.buf)
    sys.stdout.write('\033[?25l')  # hide the console's cursor
    sys.stdout.flush()
    took_over = render.console_graphics(True)
    old = termios.tcgetattr(0)
    tty.setraw(0)
    try:
        draw(canvas)
        os.read(0, 16)
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, old)
        canvas.buf[:] = before
        render.console_graphics(False)
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
    print('Screen taken over fully.' if took_over
          else 'Note: the console kept text mode (the editor will work around it).')


if __name__ == '__main__':
    main()
