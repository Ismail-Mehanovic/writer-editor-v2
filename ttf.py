"""Reads a TrueType font and draws its letters as smooth (anti-aliased)
bitmaps, with nothing but the standard library.

The Pi has no font files and no font libraries, so this does the work
itself: it reads a letter's outline from the .ttf file (straight lines and
curves, in the 'glyf' table), scales it to a pixel size, and measures how
much of every pixel the letter covers, from 0 (none) to 255 (all). The
coverage method is the signed-area accumulation from Raph Levien's font-rs.
"""

import math
import struct


class Font:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = data = f.read()
        count = struct.unpack('>H', data[4:6])[0]
        self.tables = {}
        for i in range(count):
            tag, _, offset, length = struct.unpack('>4sIII', data[12 + 16 * i:28 + 16 * i])
            self.tables[tag.decode('latin-1')] = data[offset:offset + length]
        head, hhea = self.tables['head'], self.tables['hhea']
        self.units = struct.unpack('>H', head[18:20])[0]
        long_loca = struct.unpack('>h', head[50:52])[0] == 1
        self.ascent, self.descent = struct.unpack('>hh', hhea[4:8])  # descent < 0
        metrics = struct.unpack('>H', hhea[34:36])[0]
        glyphs = struct.unpack('>H', self.tables['maxp'][4:6])[0]
        hmtx = self.tables['hmtx']
        self.advances = [struct.unpack('>H', hmtx[4 * i:4 * i + 2])[0] for i in range(metrics)]
        loca = self.tables['loca']
        if long_loca:
            self.loca = struct.unpack(f'>{glyphs + 1}I', loca[:4 * (glyphs + 1)])
        else:
            self.loca = [2 * n for n in struct.unpack(f'>{glyphs + 1}H', loca[:2 * (glyphs + 1)])]
        self.glyph_of = self._character_map()

    def _character_map(self):
        """{code point: glyph number}, from the Unicode (format 4) cmap."""
        cmap = self.tables['cmap']
        for i in range(struct.unpack('>H', cmap[2:4])[0]):
            platform, encoding, offset = struct.unpack('>HHI', cmap[4 + 8 * i:12 + 8 * i])
            if (platform, encoding) in ((3, 1), (0, 3)) and cmap[offset:offset + 2] == b'\x00\x04':
                return self._format4(cmap[offset:])
        raise ValueError('the font has no Unicode character map')

    @staticmethod
    def _format4(t):
        n = struct.unpack('>H', t[6:8])[0] // 2
        ends = struct.unpack(f'>{n}H', t[14:14 + 2 * n])
        starts = struct.unpack(f'>{n}H', t[16 + 2 * n:16 + 4 * n])
        deltas = struct.unpack(f'>{n}h', t[16 + 4 * n:16 + 6 * n])
        base = 16 + 6 * n
        offsets = struct.unpack(f'>{n}H', t[base:base + 2 * n])
        glyph_of = {}
        for s in range(n):
            for c in range(starts[s], min(ends[s], 0xFFFE) + 1):
                if offsets[s] == 0:
                    glyph_of[c] = (c + deltas[s]) & 0xFFFF
                else:
                    pos = base + 2 * s + offsets[s] + 2 * (c - starts[s])
                    g = struct.unpack('>H', t[pos:pos + 2])[0]
                    glyph_of[c] = (g + deltas[s]) & 0xFFFF if g else 0
        return glyph_of

    def outline(self, glyph):
        """The glyph's closed contours: lists of (x, y, on_curve), font units."""
        g = self.tables['glyf'][self.loca[glyph]:self.loca[glyph + 1]]
        if not g:
            return []
        contours = struct.unpack('>h', g[0:2])[0]
        return self._simple(g, contours) if contours >= 0 else self._composite(g)

    @staticmethod
    def _simple(g, contours):
        ends = struct.unpack(f'>{contours}H', g[10:10 + 2 * contours])
        points = ends[-1] + 1 if contours else 0
        pos = 10 + 2 * contours
        pos += 2 + struct.unpack('>H', g[pos:pos + 2])[0]  # skip hinting code
        flags = []
        while len(flags) < points:
            flag = g[pos]
            pos += 1
            flags.append(flag)
            if flag & 8:  # repeated
                flags += [flag] * g[pos]
                pos += 1
        coords = []
        for short, same in ((2, 16), (4, 32)):  # x, then y
            value, values = 0, []
            for flag in flags[:points]:
                if flag & short:
                    value += g[pos] if flag & same else -g[pos]
                    pos += 1
                elif not flag & same:
                    value += struct.unpack('>h', g[pos:pos + 2])[0]
                    pos += 2
                values.append(value)
            coords.append(values)
        xs, ys = coords
        result, first = [], 0
        for end in ends:
            result.append([(xs[i], ys[i], flags[i] & 1) for i in range(first, end + 1)])
            first = end + 1
        return result

    def _composite(self, g):
        """Letters built from others, such as å = a + ring."""
        result, pos = [], 10
        while True:
            flags, part = struct.unpack('>HH', g[pos:pos + 4])
            pos += 4
            if flags & 1:
                dx, dy = struct.unpack('>hh', g[pos:pos + 4])
                pos += 4
            else:
                dx, dy = struct.unpack('>bb', g[pos:pos + 2])
                pos += 2
            if not flags & 2:
                dx = dy = 0  # aligned by point numbers: rare, ignored
            a, b, c, d = 1.0, 0.0, 0.0, 1.0
            if flags & 8:
                a = d = struct.unpack('>h', g[pos:pos + 2])[0] / 16384
                pos += 2
            elif flags & 0x40:
                a, d = (v / 16384 for v in struct.unpack('>hh', g[pos:pos + 4]))
                pos += 4
            elif flags & 0x80:
                a, b, c, d = (v / 16384 for v in struct.unpack('>hhhh', g[pos:pos + 8]))
                pos += 8
            for contour in self.outline(part):
                result.append([(a * x + c * y + dx, b * x + d * y + dy, on) for x, y, on in contour])
            if not flags & 0x20:  # no more parts
                return result

    def advance(self, char, size):
        """How far the pen moves after char, in pixels, at size pixels per em."""
        glyph = self.glyph_of.get(ord(char), 0)
        return self.advances[min(glyph, len(self.advances) - 1)] * size / self.units

    def render(self, char, size):
        """Draws char at size pixels per em. Returns (left, top, width,
        height, coverage): the bitmap's offset from the pen position (top is
        how far its first row is above the baseline), its size, and one byte
        of coverage per pixel, row by row."""
        contours = self.outline(self.glyph_of.get(ord(char), 0))
        if not contours:
            return 0, 0, 0, 0, b''
        scale = size / self.units
        xs = [x for contour in contours for x, _, _ in contour]
        ys = [y for contour in contours for _, y, _ in contour]
        left, right = math.floor(min(xs) * scale), math.ceil(max(xs) * scale)
        bottom, top = math.floor(min(ys) * scale), math.ceil(max(ys) * scale)
        raster = Raster(right - left, top - bottom)
        for contour in contours:
            for start, control, end in pieces(contour):
                p0 = (start[0] * scale - left, top - start[1] * scale)
                p1 = (end[0] * scale - left, top - end[1] * scale)
                if control is None:
                    raster.line(p0, p1)
                else:
                    raster.curve(p0, (control[0] * scale - left, top - control[1] * scale), p1)
        return left, top, right - left, top - bottom, raster.coverage()


def pieces(contour):
    """A closed contour as (start, control, end) pieces: control is None for
    a straight line, else the control point of a quadratic curve. Between
    two off-curve points TrueType implies an on-curve point halfway."""
    points = [(x, y) for x, y, _ in contour]
    on = [bool(o) for _, _, o in contour]
    if not any(on):
        points.insert(0, _half(points[-1], points[0]))
        on.insert(0, True)
    first = on.index(True)
    points, on = points[first:] + points[:first + 1], on[first:] + on[:first + 1]
    result, current, control = [], points[0], None
    for point, is_on in zip(points[1:], on[1:]):
        if is_on:
            result.append((current, control, point))
            current, control = point, None
        elif control is None:
            control = point
        else:
            middle = _half(control, point)
            result.append((current, control, middle))
            current, control = middle, point
    return result


def _half(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


class Raster:
    """Coverage of a width x height bitmap, accumulated from outline edges."""

    def __init__(self, width, height):
        self.w, self.h = width, height
        self.stride = width + 2  # edges may touch one column past the right
        self.acc = [0.0] * (self.stride * height)

    def curve(self, p0, p1, p2):
        """A quadratic curve, cut into enough straight lines to look smooth."""
        dev = (p0[0] - 2 * p1[0] + p2[0]) ** 2 + (p0[1] - 2 * p1[1] + p2[1]) ** 2
        if dev < 0.333:
            self.line(p0, p2)
            return
        n = 1 + int(math.sqrt(math.sqrt(3.0 * dev)))
        previous = p0
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            point = (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                     u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])
            self.line(previous, point)
            previous = point

    def line(self, p0, p1):
        if p0[1] == p1[1]:
            return
        direction = 1.0
        if p0[1] > p1[1]:
            direction, p0, p1 = -1.0, p1, p0
        dxdy = (p1[0] - p0[0]) / (p1[1] - p0[1])
        x = p0[0] - (p0[1] * dxdy if p0[1] < 0 else 0)
        acc, stride = self.acc, self.stride
        for y in range(max(int(p0[1]), 0), min(self.h, math.ceil(p1[1]))):
            row = y * stride
            dy = min(y + 1, p1[1]) - max(y, p0[1])
            x_next = x + dxdy * dy
            d = dy * direction
            x0, x1 = (x, x_next) if x < x_next else (x_next, x)
            x0_floor = math.floor(x0)
            x0i, x1i = int(x0_floor), int(math.ceil(x1))
            if x0i < 0:
                x = x_next
                continue
            if x1i <= x0i + 1:
                middle = 0.5 * (x + x_next) - x0_floor
                acc[row + x0i] += d - d * middle
                acc[row + x0i + 1] += d * middle
            else:
                s = 1.0 / (x1 - x0)
                x0f = x0 - x0_floor
                a0 = 0.5 * s * (1.0 - x0f) ** 2
                x1f = x1 - x1i + 1.0
                am = 0.5 * s * x1f * x1f
                acc[row + x0i] += d * a0
                if x1i == x0i + 2:
                    acc[row + x0i + 1] += d * (1.0 - a0 - am)
                else:
                    a1 = s * (1.5 - x0f)
                    acc[row + x0i + 1] += d * (a1 - a0)
                    for xi in range(x0i + 2, x1i - 1):
                        acc[row + xi] += d * s
                    a2 = a1 + (x1i - x0i - 3) * s
                    acc[row + x1i - 1] += d * (1.0 - a2 - am)
                acc[row + x1i] += d * am
            x = x_next

    def coverage(self):
        out = bytearray(self.w * self.h)
        for y in range(self.h):
            total, row = 0.0, y * self.stride
            for x in range(self.w):
                total += self.acc[row + x]
                out[y * self.w + x] = min(255, int(abs(total) * 255 + 0.5))
        return bytes(out)
