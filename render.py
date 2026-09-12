"""Draws on the Pi's screen pixel by pixel.

Text characters would limit the editor to one blocky pixel font, so this
writes pixels straight into the framebuffer (/dev/fb0: 1280x800, 16 bits
per pixel) instead, with smooth letters from ttf.py. Nothing is read back
from the screen: everything is drawn onto a known background colour, which
is how the soft edges of letters and rounded corners are worked out.
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


class Canvas:
    """A screen-sized picture in the framebuffer's pixel format."""

    def __init__(self, width, height, buffer=None, stride=None):
        self.w, self.h = width, height
        self.stride = stride or width * 2
        self.buf = buffer if buffer is not None else bytearray(self.stride * height)
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
        return cls(width, height, mmap.mmap(fd, stride * height), stride)

    def fill(self, x, y, w, h, color):
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.w), min(y + h, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        row = pack(color) * (x1 - x0)
        for r in range(y0, y1):
            start = r * self.stride + 2 * x0
            self.buf[start:start + len(row)] = row

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

    def text(self, face, x, baseline, text, fg, bg, right=None):
        """Draws text on an area already painted bg, starting at x with its
        baseline at y = baseline, cut off at x = right. Returns the end x."""
        right = self.w if right is None else min(right, self.w)
        pen = float(x)
        for char in text:
            left, top, rows = self._glyph(face, char, fg, bg)
            gx = round(pen) + left
            for i, row in enumerate(rows):
                gy = baseline - top + i
                if 0 <= gy < self.h and gx >= 0:
                    row = row[:max(0, 2 * (right - gx))]
                    start = gy * self.stride + 2 * gx
                    self.buf[start:start + len(row)] = row
            pen += face.advance(char)
        return pen

    def _glyph(self, face, char, fg, bg):
        key = (id(face), char, fg, bg)
        if key not in self._blits:
            if (fg, bg) not in self._palettes:
                self._palettes[fg, bg] = [pack(blend(bg, fg, a)) for a in range(256)]
            palette = self._palettes[fg, bg]
            left, top, w, h, coverage = face.glyph(char)
            rows = [b''.join(palette[a] for a in coverage[r * w:(r + 1) * w]) for r in range(h)]
            self._blits[key] = (left, top, rows)
        return self._blits[key]

    def png(self, path):
        """Saves the picture as a PNG (for previews and tests)."""
        rows = []
        for y in range(self.h):
            line = bytearray(b'\x00')
            for (v,) in struct.iter_unpack('<H', self.buf[y * self.stride:y * self.stride + 2 * self.w]):
                line += bytes(((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31))
            rows.append(bytes(line))

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
