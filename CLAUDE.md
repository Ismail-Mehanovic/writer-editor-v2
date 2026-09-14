# Portable distraction-free writing device

A Raspberry Pi 3B+ in a custom shell that boots straight into a text editor.
Writing and editing plain text is the only function. No desktop, no browser,
no file manager.

## Hardware constraints

- Raspberry Pi 3B+, 1GB RAM, quad-core ARM Cortex-A53
- Raspberry Pi OS Lite 64-bit. No desktop environment, no X11, no Wayland.
  The editor runs on the Linux framebuffer console.
- Display: 10.1" 1280x800 DSI panel. With TerminusBold 16x32 the console is
  exactly 80 columns by 25 rows. Design for that.
- Keyboard: Keychron K2 Pro, 75% layout, Nordic (Swedish) legends, connected
  over Bluetooth. Function row and arrow keys exist; there is no numpad.
- No mouse. Ever. Don't add mouse support.
- Backlight is controllable by writing 0-255 to
  /sys/class/backlight/*/brightness

## Software constraints

- Python 3 with the curses module from the standard library.
- No pip packages. No dependencies beyond stdlib. Installing things on this
  device should never be necessary.
- Performance target: typing must feel instant on a 1.4GHz ARM core. Don't
  redraw the whole screen on every keystroke if you can redraw a line.

## Non-negotiable details

1. Swedish characters (å ä ö) must work correctly. This means calling
   locale.setlocale(locale.LC_ALL, '') at startup and using
   screen.get_wch() rather than getch() so multi-byte input is handled.
   Test this explicitly.

2. Autosave must be atomic: write to a temp file in the same directory,
   flush, os.fsync, then os.replace() over the real file. This device runs
   on a battery and has already corrupted an SD card once. A half-written
   file must be impossible.

3. Autosave must be debounced, not per-keystroke. Save roughly 2 seconds
   after typing stops. Constant small writes wear the SD card.

4. The editor must never crash to a blank screen. Wrap the main loop so
   curses.endwin() always runs on exit, and unhandled exceptions print a
   readable traceback rather than leaving a garbled terminal.

## Build stages

Build these one at a time. Do NOT jump ahead. Each stage is tested on the
actual Pi before moving on, because key codes from a real keyboard on a
real framebuffer console differ from what any desktop terminal reports.
The stages, and the design they build towards (titles, # headings, split
windows), are in PLAN.md section 8. Decided: Esc opens select mode,
documents are .md files, the console font is 16x32 (80x25).

## Status

- [x] Stage 1: Minimal editor, plus shell toggle, sleep key, boot to editor
- [x] Stage 2: Keyboard foundation
- [x] Stage 3: Cursor, with the upright cursor
- [ ] Stages 4-11 (autosave, wrap, scrolling, titles and the look,
  headings, splits, file list, select mode): built together at the
  user's request, waiting for the Pi test
- [ ] Stage 12: Undo / redo

## Working notes

- Development happens off-Pi (Windows); testing happens on the actual
  Raspberry Pi hardware. curses/get_wch behavior on the real framebuffer
  console can differ from any desktop terminal emulator, so each stage
  needs a hands-on test on the Pi before moving to the next.
- Keep main.py short and readable — this is a learning project, not just
  a deliverable.
- Built ahead of the stage order, at the user's request: Ctrl+Space
  toggles editor <-> shell both ways (shellrc binds the same key to
  "exit"), and a power key (Ctrl+Del, told apart from Del by
  console.keymap since stage 2) that sleeps/wakes the screen and shuts
  down for real after SLEEP_SHUTDOWN_MINUTES asleep.
- A halted Pi 3B+ cannot be powered on from a Bluetooth keyboard. Only
  shorting GPIO3 to GND (pins 5+6, e.g. a button) or re-plugging power
  boots it. That is why the power key sleeps instead of shutting down.
- setup.sh (run once on the Pi with sudo) sets up boot-to-editor
  (autologin on tty1 + a hook in ~/.profile opening
  the editor on ~/writing; before each login the login service loads
  console.keymap as root), the 16x32 console font,
  passwordless shutdown (/etc/sudoers.d/writer-power), a udev rule
  making the backlight writable by the video group, and a sysctl
  (kernel.printk = 1 4 1 3) that keeps kernel messages like
  "Undervoltage detected!" from printing over the editor.
- Power is a plain USB power bank: no data line, so no battery percentage
  or low-battery signal is readable. Under-voltage is not a usable proxy
  (banks hold 5 V until they cut out; the warnings come from load spikes).
  A charge display would need hardware, e.g. a battery board with a
  fuel-gauge chip on I2C.
- PLAN.md holds the roadmap (windows, titles, keys) and its stages. The
  code follows its section 7: main.py (loop, window keys, autosave),
  editor.py, filelist.py, layout.py, document.py, style.py, keys.py.
- Checked on the Pi over SSH (2026-09-12): Raspberry Pi OS on Debian 13
  (trixie), kernel 6.18, Python 3.13.5, bash 5.2, ncurses 6.5. The console
  font was TerminusBold 10x20 (128x40); the user chose 16x32 (80x25),
  which setup.sh now sets. Both font sizes have light and heavy box
  lines, arrows, ▸ and •. The 'linux' terminfo has no keypad-mode strings
  and no modified-arrow keys, so keys.py decodes key sequences itself.
- Loading a keymap or font on the console needs root on this kernel, even
  on your own tty (loadkeys: KDSKBMODE: Operation not permitted). So the
  getty@tty1 drop-in does it in ExecStartPre, never the user's login hook.
- The editor draws in pixels, not text: render.py writes the 16-bit
  framebuffer (/dev/fb0, 1280x800, RGB565) and ttf.py rasterizes the
  Selawik TTFs in fonts/ (OFL) with anti-aliasing, standard library only.
  curses only reads keys. The console is put in KD_GRAPHICS mode while
  the editor runs (back to text for the Ctrl+Space shell). Editors redraw
  only rows that changed (about 4 ms per keystroke on the Pi). Tests set
  WRITER_SCREEN=memory (never touch the real screen) and
  WRITER_SCREENSHOT=file.png to look at the result.
- The cursor blinks every 0.53 s (main.py BLINK_SECONDS; the window's
  cursor_on flag); a key shows it at once. Key waits are rounded up so
  a due blink or autosave always fires.
- Selecting: Ctrl+A, Shift+arrows, Shift+Home/End (editor.anchor);
  Ctrl+C/X/V with one clipboard shared by all editor windows
  (Editor.clipboard, in memory only). console.keymap gives
  Shift+arrows/Home/End xterm-style codes (F109-F114).
- A document scrolls as one piece (Editor.scroll, pixels): label, title,
  divider and the lone page's top edge leave with the text; line wraps
  are remembered (editor.wrapped). Long titles slide sideways while
  typed (title_shift). Canvas.clip() keeps drawing inside a window.
- The file list has no header: rows start at the top, and its place
  (breadcrumbs) is shown in the status line.
- Final polish (v1): heading # marks show only on the cursor's line;
  windows not in use are drawn dimmer (TEXT_DIM/TITLE_DIM); status-line
  key hints show only while a document is empty; scrolling down moves
  drawn pixels (Canvas.shift, Editor._shift) instead of redrawing, and
  the word count is cached per Document.version.
- Zoom: each window is drawn at its own size (Editor.zoom / FileList.zoom,
  Ctrl+plus and Ctrl+minus, console.keymap keycodes 12 and 53). The
  numbers in style.py are the full size; style.sizes(zoom) scales them
  all, fonts included, and keeps one Sizes object per zoom because the
  wrap and glyph caches are keyed on the font objects. ZOOM_DEFAULT is
  0.5: the full size is too big on the panel. A new window opens at the
  size of the one it came from; the status line is never zoomed.
- File list (filelist.py): folders under ~/writing, kept minimal (no
  icons; folders marked ›). Ctrl+F new folder, Ctrl+D new empty document
  (not opened), breadcrumbs in the status line, Tab to move (Enter on a folder or "Back to ..." drops it),
  Backspace asks, then moves the item to ~/writing/.trash (hidden, never
  emptied by the editor). A question or folder name takes every key.

## Workflow (standing instruction from the user)

- After every change: commit and push to the working branch without
  asking.
- Then, if the Pi is on, deploy: `ssh writer@writer.local`, then
  `cd ~/writer-editor-v2 && git pull`. The Pi's clone tracks the working
  branch. Use SSH key login only; never put the Pi's password in this repo.
- Deploying doesn't restart the running editor (that could lose unsaved
  text). New code takes effect at the next boot, or after Ctrl+Q + exit.
  When setup.sh changes, the user has to run `sudo sh setup.sh` on the Pi,
  because it needs their password.
