#!/usr/bin/env python3
"""Editor with a shell toggle and a power key (stages 1-3).

Type anywhere; move with the arrows, Home and End; Backspace and Del
delete. Ctrl+Q quits. Ctrl+Space toggles between the editor and a shell.
Ctrl+Del turns the screen off (sleep); pressing it again turns it back on.
Bottom row is a status line. Keys arrive through keys.py as names like
'enter' or 'ctrl-del', or as the typed character. The cursor is upright
when the font from cursor_font.py is loaded, flat otherwise.
"""

import curses
import glob
import locale
import os
import subprocess
import sys
import tempfile
import time
import traceback

import cursor_font
import keys

QUIT_KEY = 'ctrl-q'
MOVE_KEYS = ('left', 'right', 'up', 'down', 'home', 'end')

# Ctrl+Space arrives as a single null byte (showkey -a: ^@), which keys.py
# calls 'ctrl-space'. SHELL_KEY_READLINE is the same key in bash's bind
# syntax, handed to shellrc so the key also leads back from the shell to
# the editor. To change the key, change both lines.
SHELL_KEY = 'ctrl-space'
SHELL_KEY_READLINE = r'\C-@'
SHELL_RC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shellrc')

# Ctrl+Del. It only differs from plain Del once console.keymap is loaded,
# which the login service does (see setup.sh).
POWER_KEY = 'ctrl-del'

# A Pi 3B+ that has shut down can't be switched on from a Bluetooth
# keyboard, so the power key only puts it to sleep: document saved,
# backlight off, back on with the power key. Asleep this long, it shuts
# down for real so the battery can't run flat. 0 = shut down right away.
SLEEP_SHUTDOWN_MINUTES = 120
SHUTDOWN_COMMAND = ['sudo', '-n', 'shutdown', '-h', 'now']  # -n: never prompt
BACKLIGHT_GLOB = '/sys/class/backlight/*/brightness'


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
    command = [shell]
    if os.path.basename(shell) == 'bash' and os.path.exists(SHELL_RC):
        command += ['--rcfile', SHELL_RC]
    env = dict(os.environ, WRITER_SHELL_KEY=SHELL_KEY_READLINE)
    err = None
    try:
        subprocess.call(command, env=env)
    except OSError as e:
        err = str(e)
    curses.reset_prog_mode()
    screen.refresh()
    return err


def set_backlight(levels):
    """Writes each level to its brightness file and returns the old levels.
    Failures are skipped: if the backlight isn't writable (see setup.sh),
    sleep still blanks the text, the panel just stays lit."""
    old = {}
    for path, level in levels.items():
        try:
            with open(path) as f:
                old[path] = f.read().strip()
            with open(path, 'w') as f:
                f.write(level)
        except OSError:
            pass
    return old


def sleep_until_woken(screen):
    """Screen off until POWER_KEY is pressed again; other keys are ignored.
    Returns True if woken, False if SLEEP_SHUTDOWN_MINUTES ran out first."""
    old_levels = set_backlight({p: '0' for p in glob.glob(BACKLIGHT_GLOB)})
    screen.erase()
    was_visible = curses.curs_set(0)
    screen.refresh()

    deadline = time.monotonic() + SLEEP_SHUTDOWN_MINUTES * 60
    woken = False
    while not woken and time.monotonic() < deadline:
        screen.timeout(int((deadline - time.monotonic()) * 1000))
        try:
            woken = keys.read(screen) == POWER_KEY
        except curses.error:
            pass  # timed out: the deadline has passed
    screen.timeout(-1)

    # Restore even before a shutdown: systemd saves the level at shutdown
    # and would bring the screen back up nearly black on the next boot.
    set_backlight(old_levels)
    curses.curs_set(was_visible)
    return woken


def do_shutdown(screen):
    """Assumes the document has already been saved. Returns (ok, error)."""
    curses.def_prog_mode()
    curses.endwin()
    try:
        result = subprocess.run(SHUTDOWN_COMMAND, capture_output=True, text=True)
    except OSError as e:
        error = str(e)
    else:
        if result.returncode == 0:
            return True, None
        # Typically "a password is required": setup.sh fixes that.
        error = result.stderr.strip() or f'exit code {result.returncode}'
    curses.reset_prog_mode()
    screen.refresh()
    return False, error


def move_cursor(key, lines, cy, cx, want_x):
    """Where the cursor ends up after a movement key. want_x is the column
    Up and Down aim for, so the cursor keeps its column past short lines."""
    if key == 'left' and cx > 0:
        return cy, cx - 1
    if key == 'left' and cy > 0:
        return cy - 1, len(lines[cy - 1])
    if key == 'right' and cx < len(lines[cy]):
        return cy, cx + 1
    if key == 'right' and cy < len(lines) - 1:
        return cy + 1, 0
    if key == 'up':
        return (cy - 1, min(want_x, len(lines[cy - 1]))) if cy > 0 else (cy, 0)
    if key == 'down' and cy < len(lines) - 1:
        return cy + 1, min(want_x, len(lines[cy + 1]))
    if key in ('down', 'end'):
        return cy, len(lines[cy])
    if key == 'home':
        return cy, 0
    return cy, cx


def cell_text(lines, y, x):
    """The character shown at screen row y, column x (a space past the text)."""
    line = lines[y] if y < len(lines) else ''
    return line[x] if x < len(line) else ' '


def place_cursor(screen, lines, cy, cx, shown, upright):
    """Puts the cursor at text position (cy, cx) and returns the screen cell
    it is in. Until word wrap and scrolling (stages 5-6), a cursor past the
    screen's edges waits at the edge. With the upright cursor, the character
    in that cell is drawn with its bar (see cursor_font.py) and the cell
    shown before gets its plain character back."""
    max_y, max_x = screen.getmaxyx()
    y, x = min(cy, max_y - 2), min(cx, max_x - 1)
    if upright:
        curses.curs_set(0)  # the shell may have turned the flat one back on
        if shown and shown != (y, x):
            screen.addstr(*shown, cell_text(lines, *shown))
        char = cell_text(lines, y, x)
        barred = cursor_font.with_bar(char)
        if barred:
            screen.addstr(y, x, barred)
        else:
            screen.addstr(y, x, char, curses.A_REVERSE)
    screen.move(y, x)
    return y, x


def redraw_line(screen, lines, y):
    max_y, max_x = screen.getmaxyx()
    if y < max_y - 1:  # the last row is the status line
        screen.move(y, 0)
        screen.clrtoeol()
        screen.addnstr(y, 0, lines[y], max_x)


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
    for row, text in enumerate(lines[:max_y - 1]):  # last row: status line
        screen.addnstr(row, 0, text, max_x)
    draw_status(screen, filepath, dirty, message)


def main(screen, filepath):
    # Raw mode: Ctrl+C, Ctrl+Z and Ctrl+S reach the editor as keys instead
    # of killing, freezing or pausing it. Keypad mode off: keys.py decodes
    # the escape sequences itself.
    curses.raw()
    screen.keypad(False)
    upright = cursor_font.loaded()
    curses.curs_set(0 if upright else 1)
    lines = load_document(filepath)
    cy, cx = 0, 0
    want_x = 0    # the column Up and Down aim for
    shown = None  # the screen cell the cursor was last drawn in
    dirty = False
    message = ''

    redraw_all(screen, lines, filepath, dirty, message)

    while True:
        shown = place_cursor(screen, lines, cy, cx, shown, upright)
        screen.refresh()
        key = keys.read(screen)

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

        elif key == POWER_KEY:
            try:
                save_document(lines, filepath)
                dirty = False
            except OSError as e:
                message = f'save failed, not sleeping: {e}'
                draw_status(screen, filepath, dirty, message)
                continue
            if SLEEP_SHUTDOWN_MINUTES and sleep_until_woken(screen):
                message = ''
            else:
                ok, err = do_shutdown(screen)
                if ok:
                    return
                message = f'shutdown failed: {err}'
            redraw_all(screen, lines, filepath, dirty, message)

        elif key in MOVE_KEYS:
            cy, cx = move_cursor(key, lines, cy, cx, want_x)

        elif key == 'backspace':
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
                lines[cy - 1] += lines.pop(cy)
                cy -= 1
                dirty = True
                redraw_all(screen, lines, filepath, dirty, message)

        elif key == 'del':
            line = lines[cy]
            if cx < len(line):
                lines[cy] = line[:cx] + line[cx + 1:]
                if not dirty:
                    dirty = True
                    draw_status(screen, filepath, dirty, message)
                redraw_line(screen, lines, cy)
            elif cy < len(lines) - 1:
                lines[cy] += lines.pop(cy + 1)
                dirty = True
                redraw_all(screen, lines, filepath, dirty, message)

        elif key == 'enter':
            line = lines[cy]
            lines[cy] = line[:cx]
            lines.insert(cy + 1, line[cx:])
            cy += 1
            cx = 0
            dirty = True
            redraw_all(screen, lines, filepath, dirty, message)

        elif keys.is_text(key):
            line = lines[cy]
            lines[cy] = line[:cx] + key + line[cx:]
            cx += 1
            if not dirty:
                dirty = True
                draw_status(screen, filepath, dirty, message)
            redraw_line(screen, lines, cy)

        if key not in ('up', 'down'):
            want_x = cx


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    path = sys.argv[1] if len(sys.argv) > 1 else 'untitled.txt'
    try:
        curses.wrapper(main, path)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
