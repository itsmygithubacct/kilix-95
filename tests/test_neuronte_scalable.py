"""Scalable PIL masks match uncropped library output and training geometry."""
import ctypes
import importlib.util
import os
import sys
from unittest.mock import patch
import harness as H
from PIL import Image, ImageDraw, ImageFont
import neuronte_face as N
import theme as T

sys.path.insert(0, os.path.join(N._ROOT, 'train'))
import glyphs

for em in range(33, 257):
    face = N.open_size(em)
    assert face is not None, em
    assert (face.ui_top, face.rows, face.baseline) == glyphs.large_rows(em), em
for em in (33, 34, 43, 44, 64, 96):
    for bold in (False, True):
        font = T.font_at(em, bold=bold)
        face = font._face
        mask, offset = font.getmask2('Hg', '1')
        assert mask.mode == 'L' and offset == (0, 0)
        assert any(0 < p < 255 for p in mask)
        assert font.getmetrics() == (face.baseline, face.rows-face.baseline-1)
        assert font.getbbox('Hg')[3] == face.rows
        assert font.getmask2('Hg', '1', anchor='ls')[1] == (0, -face.baseline)
        w, h = mask.size
        full = (ctypes.c_uint32 * (w * 2 * em))()
        with face.lock:
            rc = N._lib.neuronte_draw_text(face.ptr, full, w, w, 2*em,
                                           0, 0, em, int(bold), b'Hg', 2, 0xFFFFFFFF)
        assert rc >= 0
        expected = bytes(p >> 24 for p in full)[face.ui_top*w:(face.ui_top+h)*w]
        assert bytes(mask) == expected, (em, bold)
        # Exercise the actual widget path requesting mode 1 with an L mask.
        canvas = Image.new('RGB', (w, h))
        draw = ImageDraw.Draw(canvas); draw.fontmode = '1'
        draw.text((0, 0), 'Hg', font=font, fill='white')
        assert canvas.getchannel('R').tobytes() == expected
        text = 'A\u2014B'
        fallback = font._fallback_font
        assert font.getlength(text) == fallback.getlength(text)
        assert bytes(font.getmask(text)) == bytes(fallback.getmask(text))
    assert isinstance(T.font_at(em, italic=True), ImageFont.FreeTypeFont)
with patch.object(N.os.path, 'isfile', return_value=False):
    assert N._load(44) is None
    assert N._load(28, True) is None
print('ok')
