#!/usr/bin/env python3
"""Minimal editor with a shell toggle and a power key (stages 1-2).

Type, backspace, Ctrl+Q to quit. Ctrl+Space toggles between the editor
and a shell. Ctrl+Del turns the screen off (sleep); pressing it again
turns it back on. Bottom row is a status line. Keys arrive through
keys.py as names like 'enter' or 'ctrl-del', or as the typed character.
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

import keys

QUIT_KEY = 'ctrl-q'

# Ctrl+Space arrives as a single null byte (showkey -a: ^@), which keys.py
# calls 'ctrl-space'. SHELL_KEY_READLINE is the same key in bash's bind
# syntax, handed to shellrc so the key also leads back from the shell to
# the editor. To change the key, change both lines.
SHELL_KEY = 'ctrl-space'
SHELL_KEY_READLINE = r'\C-@'
SHELL_RC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shellrc')

# Ctrl+Del. It only differs from plain Del once console.keymap is loaded,
# which the login hook from setup.sh does.
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
    curses.curs_set(0)
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
    curses.curs_set(1)
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
    # Raw mode: Ctrl+C, Ctrl+Z and Ctrl+S reach the editor as keys instead
    # of killing, freezing or pausing it. Keypad mode off: keys.py decodes
    # the escape sequences itself.
    curses.raw()
    screen.keypad(False)
    curses.curs_set(1)
    lines = load_document(filepath)
    cy, cx = 0, 0
    dirty = False
    message = ''

    redraw_all(screen, lines, filepath, dirty, message)

    while True:
        screen.move(cy, cx)
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
                lines[cy - 1] += lines[cy]
                del lines[cy]
                cy -= 1
                if not dirty:
                    dirty = True
                redraw_all(screen, lines, filepath, dirty, message)

        elif key == 'enter':
            line = lines[cy]
            lines[cy] = line[:cx]
            lines.insert(cy + 1, line[cx:])
            cy += 1
            cx = 0
            if not dirty:
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


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    path = sys.argv[1] if len(sys.argv) > 1 else 'untitled.txt'
    try:
        curses.wrapper(main, path)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
