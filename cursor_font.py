#!/usr/bin/env python3
"""The upright text cursor.

The Pi's console can only draw a flat cursor (an underline or a block).
This file makes a copy of the console font in which the characters people
type also exist with a bar down their left edge, stored at private-use code
points. The editor hides the console's cursor and draws the character under
it in its barred version, which looks like an ordinary upright text cursor.

Run on the Pi (setup.sh does this) to make cursor-font.psf next to this
file. The login service loads it on the screen and creates MARKER when that
worked, so the editor knows the barred characters are there:

    python3 cursor_font.py
"""

import gzip
import os
import struct
import sys

SOURCE = '/usr/share/consolefonts/Uni2-TerminusBold32x16.psf.gz'
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cursor-font.psf')
MARKER = '/run/writer-cursor-font'

# Characters that get a barred version. Anything else under the cursor is
# shown in reverse video (a block) instead.
CHARS = (''.join(map(chr, range(0x20, 0x7f)))
         + 'åäöÅÄÖéÉèÈüÜæÆøØ–—‘’“”…«»·§°')
FIRST = 0xE000           # private-use code point of CHARS[0]'s barred version
BAR_ROWS = range(2, 30)  # pixel rows of the 32 the bar covers
BAR_BITS = 0xC0          # the two leftmost pixels of a row

# Glyphs the barred ones replace, most expendable first. The console holds
# at most 512 glyphs, and the stock font already uses all of them.
EXPENDABLE = [(0x0400, 0x04FF),  # Cyrillic
              (0x0370, 0x03FF),  # Greek
              (0x2400, 0x24FF),  # control pictures, circled numbers
              (0x2600, 0x27BF),  # symbols, dingbats
              (0x2B00, 0x2BFF), (0x1E00, 0x1EFF)]
MAX_GLYPHS = 512


def with_bar(ch):
    """The private-use character that draws ch with the cursor bar, or None."""
    i = CHARS.find(ch)
    return chr(FIRST + i) if i >= 0 else None


def loaded():
    """True if the login service put the barred font on the screen."""
    return os.path.exists(MARKER)


def make(source=SOURCE, output=OUTPUT):
    """Writes the barred font to output. Returns (glyphs kept, glyphs added)."""
    with (gzip.open if source.endswith('.gz') else open)(source, 'rb') as f:
        data = f.read()
    magic, version, header, flags, count, size, height, width = struct.unpack('<8I', data[:32])
    if magic != 0x864AB572 or not flags & 1 or (width, height) != (16, 32):
        sys.exit(f'{source}: expected a 16x32 PSF2 font with a Unicode table')
    glyphs = [data[header + i * size:header + (i + 1) * size] for i in range(count)]
    entries = data[header + count * size:].split(b'\xff')[:count]
    singles = [e.split(b'\xfe')[0].decode('utf-8') for e in entries]
    glyph_of = {ch: i for i, chars in enumerate(singles) for ch in chars}
    missing = [ch for ch in CHARS if ch not in glyph_of]
    if missing:
        sys.exit(f'{source} has no glyph for {missing}')

    # The barred glyphs take over the slots of glyphs that only expendable
    # scripts use. Every other glyph keeps its slot: the console fills empty
    # cells with slot 32 and expects a space there.
    slots = []
    for low, high in EXPENDABLE:
        slots += [i for i in range(count) if i not in slots and singles[i]
                  and all(low <= ord(c) <= high for c in singles[i])]
    if len(slots) < len(CHARS):
        sys.exit(f'only room for {len(slots)} barred glyphs')

    glyphs, entries = list(glyphs), list(entries)
    for i, (ch, slot) in enumerate(zip(CHARS, slots)):
        glyph = bytearray(glyphs[glyph_of[ch]])
        for row in BAR_ROWS:
            glyph[row * 2] |= BAR_BITS  # 2 bytes per 16-pixel row
        glyphs[slot], entries[slot] = bytes(glyph), chr(FIRST + i).encode()

    font = (struct.pack('<8I', magic, version, 32, flags, count, size, height, width)
            + b''.join(glyphs) + b''.join(e + b'\xff' for e in entries))
    tmp = output + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(font)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, output)
    return count - len(CHARS), len(CHARS)


if __name__ == '__main__':
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    output = sys.argv[2] if len(sys.argv) > 2 else OUTPUT
    kept, added = make(source, output)
    print(f'wrote {output}: {kept} glyphs kept, {added} barred ones added')
