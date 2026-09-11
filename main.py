#!/usr/bin/env python3
"""Stage 1 editor plus shell-toggle and shutdown-key features.

Type, backspace, Ctrl+Q to quit. Ctrl+Space suspends to a shell and
Ctrl+Del (double-tap) shuts the device down. Bottom row is a status line.
"""

import curses
import locale
import os
import subprocess
import sys
import tempfile
import traceback

QUIT_KEY = '\x11'  # Ctrl+Q
BACKSPACE_KEYS = (curses.KEY_BACKSPACE, '\x7f', '\x08')

# showkey -a on the Pi: ^@ 0x00 -- Ctrl+Space arrives as a single null byte.
SHELL_KEY = '\x00'

# showkey -a on the Pi: ^[[3~ (0x1b 0x5b 0x33 0x7e) for Ctrl+Del. Curses'
# keypad mode (enabled by curses.wrapper) is expected to translate this
# standard "delete character" escape sequence into KEY_DC in a single
# get_wch() call. This is the one thing that most needs hardware
# verification: if the Bluetooth link ever delivers the four bytes as
# separate reads instead of one grouped key, this constant is the only
# line that needs to change.
SHUTDOWN_KEY = curses.KEY_DC

SHUTDOWN_CONFIRM_MS = 3000


def load_document(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        return ['']
    lines = text.split('\n')
    return lines if lines else ['']


def save_document(lines, filepath):
    directory = os.path.dirname(os.path.abspath(filepath)) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.tmp-', suffix='.txt')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except BaseException:
        os.remove(tmp_path)
        raise


def suspend_to_shell(screen):
    """Assumes the document has already been saved. Returns an error
    string on failure to launch, or None on success."""
    curses.def_prog_mode()
    curses.endwin()
    shell = os.environ.get('SHELL', '/bin/bash')
    err = None
    try:
        subprocess.call(shell)
    except OSError as e:
        err = str(e)
    curses.reset_prog_mode()
    screen.refresh()
    return err


def do_shutdown(screen):
    """Assumes the document has already been saved. Returns (ok, error)."""
    curses.def_prog_mode()
    curses.endwin()
    try:
        result = subprocess.call(['sudo', 'shutdown', '-h', 'now'])
    except OSError as e:
        curses.reset_prog_mode()
        screen.refresh()
        return False, str(e)
    if result != 0:
        curses.reset_prog_mode()
        screen.refresh()
        return False, f'shutdown exited with code {result}'
    return True, None


def redraw_line(screen, lines, y):
    screen.move(y, 0)
    screen.clrtoeol()
    screen.addstr(y, 0, lines[y])


def draw_status(screen, filepath, dirty, message):
    max_y, max_x = screen.getmaxyx()
    status_row = max_y - 1
    text = f'{filepath}  [{"modified" if dirty else "saved"}]'
    if message:
        text += f'  {message}'
    text = text[:max_x - 1]
    screen.move(status_row, 0)
    screen.clrtoeol()
    screen.addstr(status_row, 0, text, curses.A_REVERSE)


def redraw_all(screen, lines, filepath, dirty, message):
    screen.clear()
    max_y, max_x = screen.getmaxyx()
    content_rows = max_y - 1  # last row is reserved for the status line
    for row, text in enumerate(lines):
        if row >= content_rows:
            break
        screen.addstr(row, 0, text)
    draw_status(screen, filepath, dirty, message)


def main(screen, filepath):
    curses.curs_set(1)
    lines = load_document(filepath)
    cy, cx = 0, 0
    dirty = False
    message = ''
    awaiting_shutdown = False

    redraw_all(screen, lines, filepath, dirty, message)

    while True:
        screen.move(cy, cx)
        screen.refresh()

        try:
            key = screen.get_wch()
        except curses.error:
            if not awaiting_shutdown:
                raise
            awaiting_shutdown = False
            screen.timeout(-1)
            message = ''
            draw_status(screen, filepath, dirty, message)
            continue

        if awaiting_shutdown:
            awaiting_shutdown = False
            screen.timeout(-1)
            if key == SHUTDOWN_KEY:
                try:
                    save_document(lines, filepath)
                    dirty = False
                except OSError as e:
                    message = f'save failed, shutdown cancelled: {e}'
                    draw_status(screen, filepath, dirty, message)
                    continue
                ok, err = do_shutdown(screen)
                if ok:
                    return
                message = f'shutdown failed: {err}'
                draw_status(screen, filepath, dirty, message)
                continue
            else:
                message = ''
                draw_status(screen, filepath, dirty, message)
                # fall through: let this keystroke do its normal job below

        if key == QUIT_KEY:
            return

        elif key == SHELL_KEY:
            try:
                save_document(lines, filepath)
                dirty = False
            except OSError as e:
                message = f'save failed, not entering shell: {e}'
            else:
                err = suspend_to_shell(screen)
                message = f'shell failed: {err}' if err else ''
            redraw_all(screen, lines, filepath, dirty, message)

        elif key == SHUTDOWN_KEY:
            awaiting_shutdown = True
            message = 'shut down? press Ctrl+Del again within 3s'
            draw_status(screen, filepath, dirty, message)
            screen.timeout(SHUTDOWN_CONFIRM_MS)

        elif key in BACKSPACE_KEYS:
            if cx > 0:
                line = lines[cy]
                lines[cy] = line[:cx - 1] + line[cx:]
                cx -= 1
                if not dirty:
                    dirty = True
                    draw_status(screen, filepath, dirty, message)
                redraw_line(screen, lines, cy)
            elif cy > 0:
                cx = len(lines[cy - 1])
                lines[cy - 1] += lines[cy]
                del lines[cy]
                cy -= 1
                if not dirty:
                    dirty = True
                redraw_all(screen, lines, filepath, dirty, message)

        elif key in ('\n', '\r', curses.KEY_ENTER):
            line = lines[cy]
            lines[cy] = line[:cx]
            lines.insert(cy + 1, line[cx:])
            cy += 1
            cx = 0
            if not dirty:
                dirty = True
            redraw_all(screen, lines, filepath, dirty, message)

        elif isinstance(key, str) and key.isprintable():
            line = lines[cy]
            lines[cy] = line[:cx] + key + line[cx:]
            cx += 1
            if not dirty:
                dirty = True
                draw_status(screen, filepath, dirty, message)
            redraw_line(screen, lines, cy)


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    path = sys.argv[1] if len(sys.argv) > 1 else 'untitled.txt'
    try:
        curses.wrapper(main, path)
    except Exception:
        traceback.print_exc()
