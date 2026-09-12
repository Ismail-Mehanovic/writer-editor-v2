# Plan: from minimal editor to windowed writing app

Status: agreed 2026-09-12 (decisions in section 3). Section 8 is the build
order and CLAUDE.md points to it. One stage at a time, each tested on the
Pi first.

## 1. What the Pi's console can't do, and the workaround

| Wish | Limit on the text console | Workaround |
|---|---|---|
| Big title and # headings, as in the screenshot | One font, one size | Title and headings in bright bold white, body softer; `#` marks dimmed; a line under the title |
| The screenshot's colours | 16 colours | Redefine the console palette at startup (navy `#131B2E` background, sampled from the screenshot); reset it on exit |
| An upright text cursor | The console only draws flat cursors (underline or block) | cursor_font.py adds barred copies of typed characters to the font; the editor draws the character under the cursor with its bar (steady, not blinking) |
| Pressing Alt on its own | A modifier alone sends nothing to a terminal | Esc instead (decided) |
| Ctrl+arrows, Alt+arrows | Same codes as plain arrows by default; Alt+←/→ even switch to another console | A small keymap loaded at boot gives each combo its own code |
| Del and Ctrl+Del doing different things | Same code by default (why Del sleeps today) | Same keymap: Del deletes forward, only Ctrl+Del sleeps |
| Splitting as often as you like | 80×25 characters | Minimum window about 16 columns × 6 rows; a smaller split is refused with a message |
| Frames and symbols | The console font holds 512 glyphs | Checked on the Pi: light and heavy box lines, ← ↑ → ↓, ▸, • and … are all in it, so the select frame can be heavy |

## 2. Things an editor needs that weren't on the list

Must-haves:

- **Never losing text.** Today Ctrl+Q quits without saving, Ctrl+C kills
  the editor (unsaved text lost) and Ctrl+Z freezes it. Stages 2 and 4 fix
  this.
- **Autosave** for every document in every window (debounced, atomic).
- **Full cursor keys:** Home/End, PgUp/PgDn, Del (forward delete).
- **Undo / redo** (Ctrl+Z / Ctrl+Y).
- **Word wrap and scrolling.**
- **A key help screen (F1).** Many shortcuts, no mouse, no menus.
- **Status line:** title, saved state, word count.
- **Deleting documents** (to a trash folder), or the file list only grows.

Nice-to-haves, after the core:

- Select, cut, copy, paste (Shift+arrows), for moving paragraphs around.
- Search (Ctrl+F).
- Ctrl+End as a real shutdown, for before unplugging the battery.
- Backlight up/down (the old stage 7).

## 3. Decisions

Decided on 2026-09-12:

1. **Esc** opens select mode. (Tapping Alt would need raw keyboard access
   and Bluetooth-reconnect handling; not worth it.)
2. Documents are **`.md`** files.
3. The console font is **Terminus 16x32**: 80×25 characters, big letters.
   setup.sh sets it.

Defaults unless you say otherwise:

- Ctrl+↑/↓ and Alt+↑/↓ split above/below, allowed at any time.
- Ctrl+←/→ can't also jump by word; they're window keys now.
- The key that ends select mode is not typed into the document.
- Opening a file that's already open jumps to its window.
- Closing the last window leaves a new empty document. There is always
  at least one window.
- A duplicate title gets " (2)", " (3)", … Titles are compared ignoring
  upper/lower case, so the folder stays safe to copy to Windows or Obsidian.
- The title rule also applies when you erase an existing title: you can't
  leave it empty.
- A new document is saved only once it has a title. One that never gets
  a title leaves no file behind.
- The file list shows the most recently edited document first.

## 4. How it will look

Exact to the character at 80 columns (the 16x32 font). Heights are
shortened.

Default view, one window:

```text
       DOCUMENT
       This is the title
       ──────────────────────────────────────────────────────────────────
       This is the actual document. Text wraps inside a 66-character
       column with even margins left and right.

       # Chapter one
       It was a dark and stormy night, and the cursor blinked patiently.

 This is the title  ·  saved  ·  128 words                              F1 keys
```

After Ctrl+←, a file list on the left:

```text
 FILES                                 │ DOCUMENT
 > This is the title                   │ This is the title
   Chapter one                         │ ──────────────────────────────────────
   Letter to Anna                      │ This is the actual document, now in a
                                       │ narrower column.
                                       │
 This is the title  ·  saved                                            F1 keys
```

Select mode, left window selected:

```text
┏━ FILES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ DOCUMENT
┃ > This is the title                  ┃ This is the title
┃   Chapter one                        ┃ ──────────────────────────────────────
┃   Letter to Anna                     ┃ This is the actual document, now in a
┃                                      ┃ narrower column.
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
 arrows: pick window  ·  Backspace: close  ·  other key: type
```

Four windows:

```text
 DOCUMENT                              │ FILES
 Chapter one                           │ > Chapter one
 ───────────────────────────────────── │   Letter to Anna
 It was a dark and stormy night...     │
───────────────────────────────────────┼────────────────────────────────────────
 DOCUMENT                              │ DOCUMENT
 Letter to Anna                        │ _
 ───────────────────────────────────── │ ──────────────────────────────────────
 Dear Anna,                            │
 (new document: type a title first)
```

## 5. Keys

| Key | Where | Does |
|---|---|---|
| ← → ↑ ↓ | editor | Move the cursor (↑/↓ by screen row) |
| Home / End | editor | Start / end of the row |
| PgUp / PgDn | editor | Page up / down |
| Backspace / Del | editor | Delete before / after the cursor |
| Enter or ↓ | title | Go to the body (once the title isn't empty) |
| ↑ on the first row | body | Back to the title |
| ↑ ↓, Enter | file list | Pick, open |
| Ctrl + ← → ↑ ↓ | anywhere | Split: file list left / right / above / below |
| Alt + ← → ↑ ↓ | anywhere | Split: new document left / right / above / below |
| Esc | anywhere | Select mode |
| ← → ↑ ↓ | select mode | Move between windows |
| Backspace | select mode | Close the selected window |
| Any other key | select mode | Back to typing in the selected window |
| Ctrl+Z / Ctrl+Y | editor | Undo / redo |
| Ctrl+Space | anywhere | Shell, and back |
| Ctrl+Del | anywhere | Sleep / wake |
| F1 | anywhere | Key help |
| Ctrl+Q | anywhere | Quit to the shell |

## 6. Rules

Documents and titles:

- Everything lives in `~/writing`. A document's title is its file name:
  "Letter to Anna" is `~/writing/Letter to Anna.md`. The file holds only
  the body.
- A new document starts with the cursor in the title. The body can't be
  reached until the title has text.
- Leaving the title (Enter or ↓) creates or renames the file. If the name
  is taken, " (2)" etc. is added, and shown in the title.
- Characters a file name can't hold (`/`) aren't accepted, and a title
  can't start with a dot (that would hide the file).
- Renames are atomic and the folder is fsynced afterwards, so a power cut
  can't lose a rename.
- `#`, `##`, `###` at the start of a line make a heading. The file stores
  them as plain Markdown.
- The file list shows `.md` and `.txt` files, so the old
  `~/writing/document.txt` is still there.

Windows:

- The screen is a tree of splits. A split halves the window the cursor
  is in, in the direction of the arrow.
- Two kinds of window: editor (title and body) and file list.
- Opening a file from a file list turns that window into the file's editor.
- Every window keeps its own cursor and scroll position.
- Thin lines separate windows. In select mode the selected window gets a
  frame with its label in the top edge.
- Closing a window gives its space back to its neighbour in the split.

## 7. Code structure

Stdlib only. The code gets split into modules so that each file stays
short and readable:

```text
main.py      startup, main loop, autosave timer, shell and power keys
keys.py      raw input -> key names ('ctrl-left', 'alt-up', 'a', ...)
cursor_font.py  the upright cursor: barred glyphs in a console font
document.py  title, lines, atomic save, rename with (2)
editor.py    editor window: title field, body, cursor, wrap, scroll
filelist.py  file list window
layout.py    split tree: split, close, neighbours, rectangles
```

Each window draws into its own curses window and redraws only the rows that
changed, so typing stays instant. From stage 3 on, the editor draws into a
rectangle rather than the whole screen, which makes windows (stages 9-11)
layout work instead of a rewrite.

## 8. Stages

1. **Done.** Minimal editor. Also done: Ctrl+Space shell toggle, Ctrl+Del
   sleep, boot to editor (setup.sh), quiet console.
2. **Keyboard foundation.** console.keymap (loaded as root before each login)
   gives Ctrl/Alt+arrows and Ctrl+Del their own codes, and stops Alt+←/→
   switching consoles. keys.py decodes them. Raw mode, so Ctrl+C/Z/S
   arrive as ordinary keys. `python3 keys.py` shows the name of every key
   pressed and a line of test glyphs. setup.sh also sets the 16x32 font.
   *Pi test:* every combo shows the right name; å ä ö appear as
   themselves; Alt+← stays in the editor; box lines and · render.
3. **Cursor.** Arrows, Home/End, Del; type and delete anywhere; the
   upright cursor (cursor_font.py).
   *Pi test:* move through a paragraph containing å ä ö; insert and delete
   in the middle of it.
4. **Autosave.** Save 2 s after typing stops, atomically. Also save on
   quit, shell and sleep.
   *Pi test:* type, wait 3 s, pull the power, check the file.
5. **Word wrap** and the centered 66-column text.
   *Pi test:* a long paragraph wraps between words; ↑/↓ move by screen row.
6. **Scrolling** and PgUp/PgDn.
   *Pi test:* open a 200-line file, go to the end and back.
7. **Titles and the look.** Title field and the rules in section 6; files
   in `~/writing`; the palette, label, divider, status line with word count;
   F1 help. Boot opens a new empty document.
   *Pi test:* a new document can't reach the body without a title; a
   duplicate title gets (2); editing a title renames the file.
8. **Headings.**
   *Pi test:* `#`, `##`, `###` look different; the marks are dimmed.
9. **Windows 1.** Split tree; Alt+arrows open new documents beside, above
   or below; separator lines.
   *Pi test:* split in every direction, type in each, hit the size limit.
10. **Windows 2.** File list (Ctrl+arrows). Enter turns it into the editor;
    a file that's already open jumps to its window.
11. **Windows 3.** Select mode: arrows move between windows, Backspace
    closes.
12. **Undo / redo.**
13. **Later, in any order:** trash for deleting, select/copy/paste, search,
    Ctrl+End shutdown, backlight keys.

### Notes for stage 2

- Keycodes: Left 105, Right 106, Up 103, Down 108, Delete 111.
- Keymap lines look like `control keycode 105 = F100` and
  `string F100 = "\033[1;5D"`, using xterm-style codes (`;5` Ctrl, `;3` Alt).
  Load it after console-setup so the Swedish layout stays intact.
- Keypad mode is off; keys.py decodes escape sequences itself. After Esc
  it waits 25 ms for the rest of a sequence, so a lone Esc feels instant.
- Loading a keymap needs root on this kernel: as a normal user, even on
  your own console, loadkeys fails (KDSKBMODE: Operation not permitted).
  So the getty@tty1 drop-in loads it (ExecStartPre), not the login hook.
- Checked on the Pi (2026-09-12): Ctrl+arrows have no keymap entries
  (they send plain arrows), Alt+←/→ are Decr/Incr_Console, Alt+↑ is
  KeyboardSignal, and Ctrl+Alt+Del is Boot (reboot): don't bind that one.
- Pi software: Debian 13, Python 3.13.5, bash 5.2, ncurses 6.5.
