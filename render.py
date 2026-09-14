"""Draws on the Pi's screen pixel by pixel.

Text characters would limit the editor to one blocky pixel font, so this
writes pixels to the framebuffer (/dev/fb0: 1280x800, 16 bits per pixel)
instead, with smooth letters from ttf.py. Everything is drawn in a hidden
copy of the screen first; present() then copies only the pixel rows that
changed to the real screen, so it never shows a half-drawn line (drawing
straight onto the screen made it flicker). clip() keeps drawing inside one
window. Nothing is read back from the screen: everything is drawn onto a
known background colour, which is how the soft edges of letters and
rounded corners are worked out.
"""

import math
import os
import struct
import sys
import zlib

import ttf

KDSETMODE, KD_TEXT, KD_GRAPHICS = 0x4B3A, 0, 1
_fonts = {}


def pack(color):
    """An (r, g, b) colour as the two bytes of a 16-bit (RGB565) pixel."""
    r, g, b = color
    value = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
    return struct.pack('<H', value)


def blend(bg, fg, amount):
    """fg laid over bg with amount 0-255 of it showing."""
    return tuple(b + (f - b) * amount // 255 for b, f in zip(bg, fg))


class Face:
    """A font at one size in pixels, with an optional gap between letters."""

    def __init__(self, path, size, spacing=0.0):
        if path not in _fonts:
            _fonts[path] = ttf.Font(path)
        self.path = path
        self.font, self.size, self.spacing = _fonts[path], size, spacing
        scale = size / self.font.units
        self.ascent = round(self.font.ascent * scale)
        self.descent = round(-self.font.descent * scale)
        self._advances, self._glyphs = {}, {}

    def advance(self, char):
        if char not in self._advances:
            self._advances[char] = self.font.advance(char, self.size) + self.spacing
        return self._advances[char]

    def width(self, text):
        return sum(self.advance(c) for c in text)

    def glyph(self, char):
        if char not in self._glyphs:
            self._glyphs[char] = self.font.render(char, self.size)
        return self._glyphs[char]

    def scaled(self, zoom):
        """The same font at zoom times this size, for a zoomed window."""
        return self if zoom == 1 else Face(self.path, self.size * zoom, self.spacing * zoom)


class Canvas:
    """A screen-sized picture in the framebuffer's pixel format. screen is
    the framebuffer's memory; without one (tests) present() does nothing."""

    def __init__(self, width, height, stride=None, screen=None):
        self.w, self.h = width, height
        self.stride = stride or width * 2
        self.buf = bytearray(self.stride * height)
        self.screen = screen
        self._clip = (0, 0, width, height)  # x0, y0, x1, y1
        self._changed = []  # (first row, row after the last) of what changed
        self._blits, self._palettes = {}, {}

    @classmethod
    def framebuffer(cls, device='/dev/fb0'):
        import mmap
        info = '/sys/class/graphics/' + os.path.basename(device)

        def read(name):
            with open(f'{info}/{name}') as f:
                return f.read().strip()

        if read('bits_per_pixel') != '16':
            raise RuntimeError(f'{device} is not a 16-bit framebuffer')
        width, height = map(int, read('virtual_size').split(','))
        stride = int(read('stride'))
        fd = os.open(device, os.O_RDWR)
        return cls(width, height, stride, mmap.mmap(fd, stride * height))

    def clip(self, rect=None):
        """Keeps drawing inside rect = (x, y, width, height); None: anywhere."""
        if rect is None:
            self._clip = (0, 0, self.w, self.h)
        else:
            x, y, w, h = rect
            self._clip = (max(x, 0), max(y, 0), min(x + w, self.w), min(y + h, self.h))

    def present(self):
        """Copies the rows that changed since the last call to the screen,
        each band of rows in one go."""
        bands = sorted(self._changed)
        self._changed = []
        if self.screen is None:
            return
        merged = []
        for top, bottom in bands:
            if merged and top <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], bottom)
            elif bottom > top:
                merged.append([top, bottom])
        picture = memoryview(self.buf)
        for top, bottom in merged:
            start, end = top * self.stride, bottom * self.stride
            self.screen[start:end] = picture[start:end]

    def fill(self, x, y, w, h, color):
        cx0, cy0, cx1, cy1 = self._clip
        x0, y0 = max(x, cx0), max(y, cy0)
        x1, y1 = min(x + w, cx1), min(y + h, cy1)
        if x1 <= x0 or y1 <= y0:
            return
        row = pack(color) * (x1 - x0)
        for r in range(y0, y1):
            start = r * self.stride + 2 * x0
            self.buf[start:start + len(row)] = row
        self._changed.append((y0, y1))

    def shift(self, x, y, w, h, dy):
        """Moves the pixels of a rectangle up by dy rows (for scrolling)."""
        x0, x1 = max(x, 0), min(x + w, self.w)
        y0, y1 = max(y, 0), min(y + h, self.h)
        size = 2 * (x1 - x0)
        for row in range(y0, y1 - dy):
            source = (row + dy) * self.stride + 2 * x0
            target = row * self.stride + 2 * x0
            self.buf[target:target + size] = self.buf[source:source + size]
        self._changed.append((y0, y1))

    def rounded(self, x, y, w, h, radius, color, outside):
        """A rectangle with softly rounded corners, drawn over outside."""
        self.fill(x, y + radius, w, h - 2 * radius, color)
        for i in range(radius):
            dy = radius - i - 0.5
            inset = radius - math.sqrt(max(radius * radius - dy * dy, 0.0))
            full = math.ceil(inset)
            edge = blend(outside, color, int((full - inset) * 255))
            for row in (y + i, y + h - 1 - i):
                self.fill(x + full, row, w - 2 * full, 1, color)
                if full:
                    self.fill(x + full - 1, row, 1, 1, edge)
                    self.fill(x + w - full, row, 1, 1, edge)

    def text(self, face, x, baseline, text, fg, bg, right=None, left=None):
        """Draws text on an area already painted bg, starting at x with its
        baseline at y = baseline, cut off outside x = left..right (and the
        clip). Returns the x after the text."""
        cx0, cy0, cx1, cy1 = self._clip
        right = cx1 if right is None else min(right, cx1)
        left = cx0 if left is None else max(left, cx0)
        pen = float(x)
        top_row, bottom_row = self.h, 0
        for char in text:
            bearing, top, rows = self._glyph(face, char, fg, bg)
            gx, gy = round(pen) + bearing, baseline - top
            skip, keep = max(0, left - gx), right - gx  # pixels cut off left, kept up to right
            first, last = max(gy, cy0), min(gy + len(rows), cy1)
            if keep > skip and last > first:
                for row_y in range(first, last):
                    part = rows[row_y - gy][2 * skip:2 * keep]
                    start = row_y * self.stride + 2 * (gx + skip)
                    self.buf[start:start + len(part)] = part
                top_row, bottom_row = min(top_row, first), max(bottom_row, last)
            pen += face.advance(char)
        if bottom_row > top_row:
            self._changed.append((top_row, bottom_row))
        return pen

    def _glyph(self, face, char, fg, bg):
        key = (id(face), char, fg, bg)
        if key not in self._blits:
            if (fg, bg) not in self._palettes:
                self._palettes[fg, bg] = [pack(blend(bg, fg, a)) for a in range(256)]
            palette = self._palettes[fg, bg]
            bearing, top, w, h, coverage = face.glyph(char)
            rows = [b''.join(palette[a] for a in coverage[r * w:(r + 1) * w]) for r in range(h)]
            self._blits[key] = (bearing, top, rows)
        return self._blits[key]

    def png(self, path):
        """Saves the picture as a PNG (for previews and tests)."""
        rgb = [bytes(((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31))
               for v in range(65536)]  # every 16-bit pixel as its 3 RGB bytes
        picture = memoryview(self.buf)
        rows = [b'\x00' + b''.join(map(rgb.__getitem__,
                                       picture[y * self.stride:y * self.stride + 2 * self.w].cast('H')))
                for y in range(self.h)]

        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))

        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n'
                    + chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


def console_graphics(on):
    """Tells the console to stop (on) or resume drawing its own text and
    cursor over the pixels. Returns False if the console wouldn't."""
    try:
        import fcntl
        fcntl.ioctl(sys.stdin.fileno(), KDSETMODE, KD_GRAPHICS if on else KD_TEXT)
        return True
    except (ImportError, OSError):
        return False
