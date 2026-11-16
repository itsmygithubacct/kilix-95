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

EMS = range(1, 129)
UPRIGHT = [em for em in range(1, 33) if os.path.isfile(neuronte_face.weight_path(em))]
ITALIC = [em for em in EMS if os.path.isfile(neuronte_face.weight_path(em, True))]

def require(ready, why):
    """End this test as a skip where the Neuronte files it needs are absent."""
    if not ready:
        print("skip: %s; install Neuronte or set NEURONTE_HOME to a Neuronte checkout to run it" % why)
        raise SystemExit(0)


_TO_L = bytes.maketrans(b"#.", b"\x00\xff")


def drawing(em, italic=False):
    """{char: (advance, rows)} from font/ui-EM.txt or its italic."""
    rows, ch = {}, None
    path = neuronte_face._path("font", "ui-%d%s.txt" % (em, "-italic" if italic else ""))
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


def check_scaled(em, italic=False, chars=None):
    """Every character of the scaled face at this em, or just ``chars``, is
    what the library itself draws for it, and steps by the library's advance.

    The scaled face has no pixel drawing to compare with: one design is
    drawn at every em from 17 to 32. Upright is the library's own line of
    text; italic is the upright letter sheared by the library and stepped
    by the italic's table of advances.
    """
    import ctypes
    lib = neuronte_face._library()
    size = neuronte_face.open_size(em, italic)
    assert size is not None and not size.scalable and size.letters is not None, (em, italic)
    assert bool(size.slant) == bool(italic), (em, italic)
    regular = T.font_at(em, bold=False, italic=italic)
    bold = T.font_at(em, bold=True, italic=italic)
    assert isinstance(regular, neuronte_face.NeuronteFont), (em, italic)
    assert isinstance(bold, neuronte_face.NeuronteFont), (em, italic)
    face = ctypes.c_void_p()
    assert lib.neuronte_open_file(neuronte_face.weight_path(em, italic).encode(),
                                  ctypes.byref(face)) == 0
    assert lib.neuronte_set_binary(face, 1) == 0
    steps = face
    if italic:
        steps = ctypes.c_void_p()
        assert lib.neuronte_open_file(neuronte_face._slant_path().encode(),
                                      ctypes.byref(steps)) == 0
    try:
        for ch in (neuronte_face.COMMON if chars is None else chars):
            data = ch.encode("utf-8")
            for strike, font in ((0, regular), (1, bold)):
                adv = lib.neuronte_text_width(steps, data, len(data), strike, em)
                assert adv > 0 and T.text_w(font, ch) == adv, (em, italic, strike, ch)
                w, h = adv + em + 2, size.rows
                buf = (ctypes.c_uint32 * (w * h))()
                for dx in range(strike + 1):
                    if italic:
                        rc = lib.neuronte_draw_scalar_styled(
                            face, ctypes.cast(buf, ctypes.c_void_p), w, w, h, dx, -size.ui_top,
                            em, 2 * em, ord(ch), 0xFFFFFFFF, 2)
                    else:
                        rc = lib.neuronte_draw_text(
                            face, ctypes.cast(buf, ctypes.c_void_p), w, w, h, dx, -size.ui_top,
                            em, 0, data, len(data), 0xFFFFFFFF)
                    assert rc >= 0, (em, italic, ch, rc)
                want = Image.new("1", (w, h), 0)
                want.putdata([1 if px else 0 for px in buf])
                mask, _ = font.getmask2(ch, "1")
                got = Image.new("1", mask.size, 0)
                got.im.paste(1, (0, 0) + mask.size, mask)
                box = want.getbbox()
                assert got.getbbox() == box, (em, italic, strike, ch, got.getbbox(), box)
                if box:
                    assert got.crop(box).tobytes() == want.crop(box).tobytes(), \
                        (em, italic, strike, ch)
    finally:
        lib.neuronte_close(face)
        if italic:
            lib.neuronte_close(steps)


def check(em, italic=False, chars=None):
    """Every character of that face, or just ``chars``, is its drawing; for
    an em the scaled face draws, it is what the library draws."""
    if neuronte_face.kind(em, italic) == "scaled":
        return check_scaled(em, italic, chars)
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
