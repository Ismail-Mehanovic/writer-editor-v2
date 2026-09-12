#!/usr/bin/env python3
"""The writing device's editor: one screen of windows, each showing either
a document (editor.py) or the list of documents (filelist.py).

    Ctrl+arrow    open a file list beside the current window
    Alt+arrow     open a new document beside the current window
    Esc           select mode: arrows pick a window, Backspace closes it,
                  any other key goes back to typing
    Ctrl+Space    shell, and back       Ctrl+Del   sleep / wake
    Ctrl+Q        save everything and quit

Documents are saved 2 seconds after typing stops, and before anything that
leaves the editor (shell, sleep, quit, closing a window).
"""

import curses
import glob
import locale
import os
import subprocess
import sys
import time
import traceback

import cursor_font
import document
import keys
import layout
import style
from editor import Editor
from filelist import FileList

QUIT_KEY = 'ctrl-q'
SELECT_KEY = 'esc'
FILES_KEYS = {'ctrl-left': 'left', 'ctrl-right': 'right',
              'ctrl-up': 'up', 'ctrl-down': 'down'}
NEW_DOCUMENT_KEYS = {'alt-left': 'left', 'alt-right': 'right',
                     'alt-up': 'up', 'alt-down': 'down'}
AUTOSAVE_SECONDS = 2

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
# keyboard, so the power key only puts it to sleep: documents saved,
# backlight off, back on with the power key. Asleep this long, it shuts
# down for real so the battery can't run flat. 0 = shut down right away.
SLEEP_SHUTDOWN_MINUTES = 120
SHUTDOWN_COMMAND = ['sudo', '-n', 'shutdown', '-h', 'now']  # -n: never prompt
BACKLIGHT_GLOB = '/sys/class/backlight/*/brightness'


def suspend_to_shell(screen):
    """Returns an error string on failure to launch, or None on success."""
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
    style.set_palette()  # leaving curses reset the colours to the console's own
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
    return woken


def do_shutdown(screen):
    """Assumes everything is saved. Returns (ok, error)."""
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
    style.set_palette()
    screen.refresh()
    return False, error


def draw_frame(screen, rect, label):
    """The thin frame select mode puts around the chosen window."""
    y, x, h, w = rect
    screen.addnstr(y, x, f'┌─ {label} '.ljust(w - 1, '─') + '┐', w, style.FRAME)
    for row in range(y + 1, y + h - 1):
        screen.addstr(row, x, '│', style.FRAME)
        screen.addstr(row, x + w - 1, '│', style.FRAME)
    screen.addnstr(y + h - 1, x, '└' + '─' * (w - 2) + '┘', w, style.FRAME)


# A line cell's directions (up, down, left, right) and the character for them.
STEPS = {'u': (-1, 0, 'd'), 'd': (1, 0, 'u'), 'l': (0, -1, 'r'), 'r': (0, 1, 'l')}
LINE_CHARS = {'ud': '│', 'lr': '─', 'dlr': '┬', 'ulr': '┴', 'udr': '├', 'udl': '┤', 'udlr': '┼'}


def draw_lines(screen, lines):
    """The thin lines between windows (from Layout.place), joined where
    they meet, so they look like the line under a document's title."""
    cells = {}
    for kind, y, x, length in lines:
        for i in range(length):
            cells[(y + i, x) if kind == '|' else (y, x + i)] = set('ud' if kind == '|' else 'lr')
    for (y, x), directions in list(cells.items()):
        for d in list(directions):
            dy, dx, back = STEPS[d]
            if (y + dy, x + dx) in cells:
                cells[(y + dy, x + dx)].add(back)
    for (y, x), directions in cells.items():
        char = LINE_CHARS[''.join(sorted(directions, key='udlr'.index))]
        screen.addstr(y, x, char, style.LINE)


class Writer:
    def __init__(self, screen, folder):
        self.screen, self.folder = screen, folder
        self.layout = layout.Layout(self.new_editor())
        self.selecting = False
        self.message = ''
        self.upright = cursor_font.loaded()

    def new_editor(self, path=None):
        return Editor(document.Document(path, folder=self.folder))

    def editors(self):
        return [w for w in self.layout.windows() if isinstance(w, Editor)]

    def places(self):
        height, width = self.screen.getmaxyx()
        return self.layout.place(0, 0, height - 1, width)  # last row: status

    # ---- the loop

    def run(self):
        self.draw()
        while True:
            key = self.read_key()
            if key is None:  # autosaved, or a key with no name
                self.draw(only_focus=True)
                continue
            self.message = ''
            result = self.handle(key)
            if result == 'quit':
                return
            self.draw(only_focus=not result)

    def read_key(self):
        """The next key, waiting at most until an autosave is due."""
        due = [e.doc.edited_at + AUTOSAVE_SECONDS for e in self.editors()
               if e.doc.dirty and e.doc.path]
        if due:
            self.screen.timeout(max(0, int((min(due) - time.monotonic()) * 1000)))
        try:
            return keys.read(self.screen)
        except curses.error:
            self.save(only_due=True)
            return None
        finally:
            self.screen.timeout(-1)

    def save(self, only_due=False):
        now = time.monotonic()
        for doc in (e.doc for e in self.editors()):
            if doc.dirty and doc.path and (not only_due or now - doc.edited_at >= AUTOSAVE_SECONDS):
                try:
                    doc.save()
                except OSError as e:
                    self.message = f'Could not save "{doc.title}": {e}'

    # ---- keys

    def handle(self, key):
        """Acts on one key. Returns 'quit', True to redraw everything, or
        False to redraw only the focused window."""
        if self.selecting:
            return self.select_key(key)
        if key == QUIT_KEY:
            self.save()
            return 'quit'
        if key == SHELL_KEY:
            self.save()
            err = suspend_to_shell(self.screen)
            self.message = f'Shell failed: {err}' if err else ''
            return True
        if key == POWER_KEY:
            self.save()
            if SLEEP_SHUTDOWN_MINUTES and sleep_until_woken(self.screen):
                return True
            ok, err = do_shutdown(self.screen)
            if ok:
                return 'quit'
            self.message = f'Shutdown failed: {err}'
            return True
        if key == SELECT_KEY:
            self.selecting = True
            return True
        if key in FILES_KEYS:
            return self.split(FileList(self.folder), FILES_KEYS[key])
        if key in NEW_DOCUMENT_KEYS:
            return self.split(self.new_editor(), NEW_DOCUMENT_KEYS[key])

        focus = self.layout.focus
        if isinstance(focus, FileList):
            path = focus.handle(key)
            if path:
                self.open(path, focus)
            return bool(path)
        was_in_title = focus.in_title
        try:
            self.message = focus.handle(key) or ''
        except OSError as e:
            self.message = f'Could not save the title: {e}'
        return was_in_title and not focus.in_title  # a title set: lists change

    def split(self, window, direction):
        rects, _ = self.places()
        if not self.layout.split(window, direction, rects[self.layout.focus]):
            self.message = 'No room for another window there.'
        return True

    def open(self, path, file_list):
        """The file list turns into the document's editor. If the document
        is already open elsewhere, the list closes and that window gets the
        focus instead, so a document is never edited in two places."""
        for editor in self.editors():
            if editor.doc.path == path:
                self.layout.close(file_list)
                self.layout.focus = editor
                return
        self.layout.swap(file_list, self.new_editor(path))

    def select_key(self, key):
        if key in ('left', 'right', 'up', 'down'):
            rects, _ = self.places()
            self.layout.focus = self.layout.neighbour(key, rects) or self.layout.focus
        elif key == 'backspace':
            closing = self.layout.focus
            self.save()
            if not self.layout.close(closing):  # the last one: start afresh
                self.layout.swap(closing, self.new_editor())
        else:
            self.selecting = False
        return True

    # ---- drawing

    def draw(self, only_focus=False):
        rects, lines = self.places()
        alone = len(rects) == 1
        if only_focus:
            windows = [self.layout.focus]
        else:
            self.screen.erase()
            draw_lines(self.screen, lines)
            windows = list(rects)
            for window in windows:
                if isinstance(window, FileList):
                    window.reload()
        cursor = None
        for window in windows:
            focused = window is self.layout.focus and not self.selecting
            cell = window.draw(self.screen, rects[window], focused, alone, self.upright)
            cursor = cell or cursor
        if self.selecting:
            label = 'FILES' if isinstance(self.layout.focus, FileList) else 'DOCUMENT'
            draw_frame(self.screen, rects[self.layout.focus], label)
        self.draw_status()
        if cursor and not self.upright:
            curses.curs_set(1)
            self.screen.move(*cursor)
        else:
            curses.curs_set(0)
        self.screen.refresh()

    def draw_status(self):
        height, width = self.screen.getmaxyx()
        focus = self.layout.focus
        if self.selecting:
            text = 'Arrows: pick a window  ·  Backspace: close it  ·  other keys: type'
        elif self.message:
            text = self.message
        elif isinstance(focus, FileList):
            text = 'Up/Down: pick a document  ·  Enter: open it  ·  Esc: windows'
        elif focus.in_title:
            text = 'Type a title, then press Enter.'
        else:
            state = 'editing' if focus.doc.dirty else 'saved'
            text = f'{focus.title}  ·  {state}  ·  {focus.words()} words'
        self.screen.addnstr(height - 1, 0, (' ' + text).ljust(width - 1), width - 1, style.STATUS)


def main(screen, folder):
    # Raw mode: Ctrl+C, Ctrl+Z and Ctrl+S reach the editor as keys instead
    # of killing, freezing or pausing it. Keypad mode off: keys.py decodes
    # the escape sequences itself.
    curses.raw()
    screen.keypad(False)
    style.init()
    style.set_palette()
    screen.bkgd(' ', style.BACKDROP)
    os.makedirs(folder, exist_ok=True)
    Writer(screen, folder).run()


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    folder = sys.argv[1] if len(sys.argv) > 1 else document.WRITING_DIR
    if os.path.isfile(folder):  # an older login hook passed a document
        folder = os.path.dirname(os.path.abspath(folder))
    style.set_palette()
    try:
        curses.wrapper(main, folder)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    finally:
        style.reset_palette()
