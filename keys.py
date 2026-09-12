#!/usr/bin/env python3
"""Turns raw keyboard input into key names.

The editor reads the console with curses' keypad mode off and decodes
escape sequences here, because the combinations it needs (Ctrl/Alt+arrows,
Ctrl+Del) aren't in the 'linux' terminfo entry. console.keymap makes the
console send them. Run this file on its own to see what every key is
called on the real keyboard:

    python3 keys.py
"""

import curses
import locale

ESC_WAIT_MS = 25  # after Esc, how long to wait for the rest of a sequence

# What follows Esc in the sequences the Pi's console sends.
SEQUENCES = {
    '[A': 'up', '[B': 'down', '[C': 'right', '[D': 'left',
    '[1~': 'home', '[2~': 'insert', '[3~': 'del', '[4~': 'end',
    '[5~': 'pgup', '[6~': 'pgdn',
    '[[A': 'f1', '[[B': 'f2', '[[C': 'f3', '[[D': 'f4', '[[E': 'f5',
    '[17~': 'f6', '[18~': 'f7', '[19~': 'f8', '[20~': 'f9',
    '[21~': 'f10', '[23~': 'f11', '[24~': 'f12',
    # These only come once console.keymap is loaded.
    '[1;5A': 'ctrl-up', '[1;5B': 'ctrl-down',
    '[1;5C': 'ctrl-right', '[1;5D': 'ctrl-left',
    '[1;3A': 'alt-up', '[1;3B': 'alt-down',
    '[1;3C': 'alt-right', '[1;3D': 'alt-left',
    '[3;5~': 'ctrl-del',
    '[1;2A': 'shift-up', '[1;2B': 'shift-down',
    '[1;2C': 'shift-right', '[1;2D': 'shift-left',
    '[1;2H': 'shift-home', '[1;2F': 'shift-end',
}

CONTROL_KEYS = {
    '\x00': 'ctrl-space', '\t': 'tab', '\n': 'enter', '\r': 'enter',
    '\x08': 'backspace', '\x7f': 'backspace', '\x1b': 'esc',
}

GLYPHS = '─│┌┐└┘├┤┬┴┼ ━┃┏┓┗┛ ← ↑ → ↓ ▸ • … · å ä ö Å Ä Ö é ü'


def read(screen):
    """Waits for one keypress and returns its name (see name())."""
    return name(read_raw(screen))


def is_text(key):
    """True if key is a character to insert rather than a named key."""
    return key is not None and len(key) == 1 and key.isprintable()


def read_raw(screen):
    """Waits for one keypress and returns the characters the console sent
    for it, like 'a' or '\\x1b[1;5D'; None for curses' own codes such as a
    resize. A timeout set on screen applies to the wait (curses.error when
    it runs out). After an Esc, screen is left blocking."""
    ch = screen.get_wch()
    if not isinstance(ch, str):
        return None
    if ch != '\x1b':
        return ch
    # The rest of a sequence is already waiting; after a lone Esc nothing is.
    screen.timeout(ESC_WAIT_MS)
    try:
        while not complete(ch[1:]):
            more = screen.get_wch()
            if not isinstance(more, str):
                break
            ch += more
    except curses.error:
        pass  # nothing more came: a lone Esc
    finally:
        screen.timeout(-1)
    return ch


def complete(rest):
    """True once rest, what followed Esc, is a whole sequence."""
    if rest in ('', '[', '[['):
        return False
    if not rest.startswith('['):
        return True  # Alt+key: Esc, then the key
    return rest[-1] == '~' or rest[-1].isalpha()


def name(raw):
    """'left', 'ctrl-left', 'alt-x', 'ctrl-q', 'enter', ... for special
    keys; the character itself for text (å ä ö included); None for
    anything unknown."""
    if not raw:
        return None
    if len(raw) > 1:  # Esc and what followed it
        rest = raw[1:]
        if rest in SEQUENCES:
            return SEQUENCES[rest]
        if len(rest) == 1 and name(rest):  # Alt+key
            return 'alt-' + name(rest)
        return None
    if raw in CONTROL_KEYS:
        return CONTROL_KEYS[raw]
    if raw < ' ':
        return 'ctrl-' + chr(ord(raw) + 64).lower()
    return raw


def test(screen):
    """Shows the name and codes of every key pressed. Ctrl+Q quits."""
    curses.raw()
    screen.keypad(False)
    max_y, max_x = screen.getmaxyx()
    header = ['Key test. Press keys to see their names. Ctrl+Q quits.',
              f'Glyphs: {GLYPHS}',
              f'Screen: {max_x} columns x {max_y} rows', '']
    log = []
    while True:
        screen.erase()
        for y, text in enumerate(header + log[-(max_y - len(header)):]):
            screen.addstr(y, 0, text[:max_x - 1])
        screen.refresh()
        raw = read_raw(screen)
        if raw is None:
            continue
        key = name(raw)
        codes = ' '.join(f'{ord(c):02x}' for c in raw)
        log.append(f'{key or "(unknown)":<14} {codes}')
        if key == 'ctrl-q':
            return


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    curses.wrapper(test)
