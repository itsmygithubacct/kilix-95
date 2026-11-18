"""Unsupported graphemes and layout requests use the same whole-text fallback."""
from unittest.mock import patch
import harness as H
from PIL import ImageFont, features
import neuronte_face as N
import theme as T
from neuronte_face_check import require

require(all(N.open_size(em, italic) for em, italic in ((11, False), (16, True), (64, False)))
        and N._library().has_stroke,
        "no Neuronte 11px, 16px italic or large weights, or a library without strokes")

clusters = ('e\u0301', 'A\u0323\u0301B', '\u2764\ufe0f', '\U0001f1ec\U0001f1e7',
            '\U0001f469\u200d\U0001f4bb', 'fi\u200d', 'A\u00e9B')
for em, italic in ((11,False),(16,True),(64,False)):
    for bold in (False,True):
        font = T.font_at(em,bold=bold,italic=italic)
        assert isinstance(font,N.NeuronteFont)
        fallback = font._fallback_font
        for text in clusters:
            assert not font._use_face(text)
            assert font.getlength(text) == fallback.getlength(text)
            assert font.getbbox(text) == fallback.getbbox(text)
            actual,offset = font.getmask2(text,'L',anchor='ls')
            expected,expected_offset = fallback.getmask2(text,'L',anchor='ls')
            assert actual.size == expected.size and bytes(actual) == bytes(expected)
            assert offset == expected_offset
        # Outlining is a real rendering request, not extra reported padding.
        kwargs = {'stroke_width':2,'anchor':'ls'}
        assert font.getbbox('Hg',**kwargs) == fallback.getbbox('Hg',**kwargs)
        actual,offset = font.getmask2('Hg','L',**kwargs)
        expected,expected_offset = fallback.getmask2('Hg','L',**kwargs)
        assert actual.size == expected.size and bytes(actual) == bytes(expected)
        assert offset == expected_offset
        if features.check('raqm'):
            for options in ({'direction':'rtl'}, {'features':['-kern']}, {'language':'en'}):
                assert font.getlength('AV fi',**options) == fallback.getlength('AV fi',**options)
                assert font.getbbox('AV fi',**options) == fallback.getbbox('AV fi',**options)
                a,off = font.getmask2('AV fi','L',**options)
                b,want = fallback.getmask2('AV fi','L',**options)
                assert a.size == b.size and bytes(a) == bytes(b) and off == want

# No italic net is claimed for tiny indistinguishable drawings or scalable
# italic. The fallback remains a real font of the requested style.
for em in (1,2,33,64,128):
    for bold in (False,True):
        font = T.font_at(em,bold=bold,italic=True)
        assert isinstance(font,ImageFont.FreeTypeFont), (em,bold)
        assert 'Oblique' in str(font.path)

# A library without the new scalable stroke APIs still serves ordinary
# sizes, but requests a true bold fallback for the unavailable operation.
font = T.font_at(64,bold=True)
with patch.object(N._lib,'has_stroke',False):
    assert N.try_font(64,True,font._fallback_font,T.font_at) is None
    assert N.try_font(64,False,T.font_at(64)._fallback_font,T.font_at) is not None

# The rich-text consumer must select the fallback for an entire styled run
# before measuring prefixes, placing a caret, or computing baseline metrics.
# Otherwise the ASCII prefix uses neural widths while the drawn line uses
# DejaVu, and fallback accents can be clipped by smaller neural ascenders.
from apps.wordpad import RichTextArea, DEFAULT, _run
rta = RichTextArea(0,0,500,200)
text = 'AAAA e\u0301g'
rta.set_doc([[_run(text,dict(DEFAULT,size=16))]])
rta._ensure_layout()
vl = rta._vlines[0]
fallback = T.font_at(16)._fallback_font
assert rta._x_of(vl,4) == int(fallback.getlength('AAAA'))
xs,offs = rta._xtable(vl)
assert xs[offs.index(4)] == int(fallback.getlength('AAAA'))
assert (vl['asc'],vl['desc']) == fallback.getmetrics()
print('ok')
