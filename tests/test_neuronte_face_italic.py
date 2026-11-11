"""WordPad's Oblique and BoldOblique through the Neuronte italic face.

Every glyph, regular and bold, of each WordPad size with an italic file is
its italic drawing. A size with no italic file is DejaVu Oblique.
"""
import harness as H          # noqa: F401  sets up the desktop path
from PIL import ImageFont

import neuronte_face
from apps.wordpad import SIZES, _font
from neuronte_face_check import ITALIC, check

for em in sorted(int(s) for s in SIZES):
    for bold in (False, True):
        font = _font(bold, True, em)
        if em in ITALIC:
            assert isinstance(font, neuronte_face.NeuronteFont), (em, bold)
            assert font.italic
        else:
            assert isinstance(font, ImageFont.FreeTypeFont), (em, bold)
    if em in ITALIC:
        check(em, italic=True)

print("ok")
