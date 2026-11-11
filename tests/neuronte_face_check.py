"""Shared pixel check for the Neuronte desktop face tests.

Each glyph is drawn through the PIL font the desktop uses, regular and
bold, and compared whole with the drawing it was trained from: rows 0 to
em-1 are the drawing at the pen and every other pixel is clear. Bold is
the drawing struck again one pixel to the right.
"""
import os

from PIL import Image, ImageDraw

import neuronte_face
import theme as T

ROOT = os.environ.get("NEURONTE_HOME") or "/home/pleb/projects/neuronte"
EMS = range(1, 129)
UPRIGHT = [em for em in range(1, 33) if os.path.isfile(neuronte_face.weight_path(em))]
ITALIC = [em for em in EMS if os.path.isfile(neuronte_face.weight_path(em, True))]

_TO_L = bytes.maketrans(b"#.", b"\x00\xff")


def drawing(em, italic=False):
    """{char: (advance, rows)} from font/ui-EM.txt or its italic."""
    rows, ch = {}, None
    path = os.path.join(ROOT, "font", "ui-%d%s.txt" % (em, "-italic" if italic else ""))
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            # A bare "#" is a comment before the first character and a row
            # of one inked pixel after it.
            if line.startswith("# ") or not line or (line == "#" and ch is None):
                continue
            if " " in line:
                name, adv = line.split(" ", 1)
                ch = chr(int(name[2:], 16)) if name.startswith("U+") else name
                rows[ch] = (int(adv), [])
            else:
                rows[ch][1].append(line)
    return rows


def _ink(font, text):
    width = int(font.getlength(text)) + font.size + 4
    height = font.size + 4
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    draw.text((0, 0), text, font=font, fill=(0, 0, 0))
    return img


def _want(rows, size):
    """The image a drawing should make, as L bytes of this size."""
    width, height = size
    out = bytearray(b"\xff" * (width * height))
    for y, row in enumerate(rows):
        line = row.encode().translate(_TO_L)
        out[y * width:y * width + len(line)] = line
    return bytes(out)


def _struck(row):
    """A row struck twice, one pixel apart: one pixel wider."""
    return "".join("#" if a == "#" or b == "#" else "."
                   for a, b in zip(row + ".", "." + row))


def check(em, italic=False, chars=None):
    """Every character of that face, or just ``chars``, is its drawing."""
    art = drawing(em, italic)
    regular = T.font_at(em, bold=False, italic=italic)
    bold = T.font_at(em, bold=True, italic=italic)
    assert isinstance(regular, neuronte_face.NeuronteFont), (em, italic)
    assert isinstance(bold, neuronte_face.NeuronteFont), (em, italic)
    for ch in (art if chars is None else chars):
        adv, rows = art[ch]
        assert rows and max(len(r) for r in rows) > 0, (em, italic, ch)
        assert T.text_w(regular, ch) == adv, (em, italic, ch)
        assert T.text_w(bold, ch) == adv + 1, (em, italic, ch)
        got = _ink(regular, ch)
        assert got.convert("L").tobytes() == _want(rows, got.size), (em, italic, ch)
        got = _ink(bold, ch)
        assert got.convert("L").tobytes() == _want([_struck(r) for r in rows], got.size), \
            (em, italic, "bold", ch)
