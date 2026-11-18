"""The desktop face: Neuronte where a weight file exists, DejaVu otherwise.

Wiring, and the pixel check of every glyph, regular and bold, at the
upright sizes the desktop asks for: chrome, Calc and the WordPad menu.
test_neuronte_face_italic.py checks WordPad's italic, and
test_neuronte_face_sizes.py every other packed size. A size or style with
no file stays DejaVu, or DejaVu Oblique for italic.
"""
import os

import harness as H          # noqa: F401  sets up the desktop path
from PIL import ImageFont

import neuronte_face
import theme as T
from apps.wordpad import SIZES, _font
from apps.charmap import BIG
from neuronte_face_check import EMS, ITALIC, UPRIGHT, check, require

# The path the pty worker reopens is a real TrueType file.
assert os.path.isfile(T.FONT.path), T.FONT.path
reopened = ImageFont.truetype(T.FONT.path, 11)
assert isinstance(reopened, ImageFont.FreeTypeFont)

# Without Neuronte (none installed and no NEURONTE_HOME) the chrome keeps
# DejaVu; the rest of this test needs the Neuronte files.
if neuronte_face._library() is None or 11 not in UPRIGHT:
    for font in (T.FONT, T.BOLD, T.SMALL):
        assert isinstance(font, ImageFont.FreeTypeFont), font
require(neuronte_face._library() is not None and 11 in UPRIGHT,
        "no Neuronte library or 11px weights")

# Chrome sizes are the face. Bold is the same file, struck twice.
assert isinstance(T.FONT, neuronte_face.NeuronteFont)
assert isinstance(T.BOLD, neuronte_face.NeuronteFont)
assert isinstance(T.SMALL, neuronte_face.NeuronteFont)
assert T.FONT.size == 11 and T.BOLD.size == 11 and T.SMALL.size == 10
assert T.BOLD.bold == 1 and T.FONT.bold == 0

# Every size with a weight file is the face, and no other is: a size with
# no file is not pretended.
for em in EMS:
    for italic in (False, True):
        packed = (em in ITALIC if italic else os.path.isfile(neuronte_face.weight_path(em)))
        assert (neuronte_face.open_size(em, italic) is not None) == packed, (em, italic)
assert 10 in UPRIGHT and 11 in UPRIGHT
for em in (8, 9):   # WordPad's two smallest sizes
    want = neuronte_face.NeuronteFont if em in UPRIGHT else ImageFont.FreeTypeFont
    assert isinstance(_font(False, False, em), want), em
# Charmap uses the scalable face at 44 px.
assert BIG.size == 44
assert isinstance(BIG, neuronte_face.NeuronteFont)

# WordPad's Oblique and BoldOblique: the italic file where there is one,
# with the DejaVu oblique as its path and fallback; DejaVu oblique where not.
for em in (11, next(e for e in EMS if e not in ITALIC)):
    for bold in (False, True):
        italic = _font(bold, True, em)
        assert "Oblique" in os.path.basename(italic.path), (em, bold, italic.path)
        assert os.path.isfile(italic.path)
        if em in ITALIC:
            assert isinstance(italic, neuronte_face.NeuronteFont), (em, bold)
            assert italic.italic and italic.bold == int(bold)
            assert isinstance(italic.font_variant(size=em), neuronte_face.NeuronteFont)
            assert italic.font_variant(size=em).italic
        else:
            assert isinstance(italic, ImageFont.FreeTypeFont), (em, bold, type(italic))

# A character the face does not cover is measured with DejaVu.
emdash = "\u2014"
assert T.text_w(T.FONT, emdash) == int(reopened.getlength(emdash))
assert T.text_w(T.FONT, "Start") != int(reopened.getlength("Start"))

# Pads the old 58 / 64 / 76 constants left around DejaVu, plus the new advances.
assert T.START_W == 24 + T.text_w(T.BOLD, "Start") + 3
T.apply_flavor("xp")
assert T.START_W == 24 + T.text_w(T.BOLD, "start") + 11
T.apply_flavor("95")
widest = max(T.text_w(T.FONT, f"{hour:02d}:{minute:02d} {suffix}")
             for hour in range(1, 13) for minute in range(60)
             for suffix in ("AM", "PM"))
assert T.CLOCK_W == 18 + widest + 7

# Anchor la is the ascender. Anchor ls is the baseline row.
_, la = T.FONT.getmask2("H", "1")
_, ls = T.FONT.getmask2("H", "1", anchor="ls")
assert la == (0, 0)
assert ls == (0, -T.FONT.getmetrics()[0])

# The sizes the desktop asks for: chrome 10 and 11, Calc's 18, and the
# WordPad menu. Each packed one is its drawing, every character.
if UPRIGHT:
    for em in sorted({10, 11, 18} | {int(s) for s in SIZES}):
        if em in UPRIGHT:
            check(em)

print("ok")
