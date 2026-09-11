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

1. Minimal curses window. Type characters, see them appear, Ctrl+Q quits
   cleanly. Backspace works. That's all.
2. Swedish characters verified working.
3. Word wrap, and a centered text column of about 66 characters with even
   margins left and right.
4. Debounced atomic autosave to a file passed as a command-line argument.
5. Scrolling for documents longer than the visible 25 lines.
6. Ctrl+Space suspends curses and drops to a shell; exiting the shell
   returns to the document with text intact. Note: Ctrl+Space sends a null
   byte and some terminals swallow it, so make the key easy to change.
7. Keybindings for backlight up/down and clean shutdown
   (sudo shutdown -h now).

## Status

- [x] Stage 1: Minimal curses window (main.py)
- [ ] Stage 2: Swedish characters
- [ ] Stage 3: Word wrap + centered column
- [ ] Stage 4: Debounced atomic autosave
- [ ] Stage 5: Scrolling
- [ ] Stage 6: Shell suspend
- [ ] Stage 7: Backlight + shutdown keybindings

## Working notes

- Development happens off-Pi (Windows); testing happens on the actual
  Raspberry Pi hardware. curses/get_wch behavior on the real framebuffer
  console can differ from any desktop terminal emulator, so each stage
  needs a hands-on test on the Pi before moving to the next.
- Keep main.py short and readable — this is a learning project, not just
  a deliverable.
- Built ahead of the stage order, at the user's request: Ctrl+Space
  toggles editor <-> shell both ways (shellrc binds the same key to
  "exit"), and a power key (Ctrl+Del; the console sends the same bytes
  for plain Del) that sleeps/wakes the screen and shuts down for real
  after SLEEP_SHUTDOWN_MINUTES asleep.
- A halted Pi 3B+ cannot be powered on from a Bluetooth keyboard. Only
  shorting GPIO3 to GND (pins 5+6, e.g. a button) or re-plugging power
  boots it. That is why the power key sleeps instead of shutting down.
- setup.sh (run once on the Pi with sudo) sets up boot-to-editor
  (autologin on tty1 + a hook in ~/.profile opening ~/writing/document.txt),
  passwordless shutdown (/etc/sudoers.d/writer-power), and a udev rule
  making the backlight writable by the video group.
