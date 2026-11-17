"""KILIX_NEURONTE_ONLY=1: no font file is opened, and a character the face
does not cover is a terminal bundle's cell or the library's untrained mark.

Needs a Neuronte 2.2 tree (NEURONTE_HOME) with neuronte-split-v9.nrt; it is
skipped where the tree has no terminal bundle.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = r'''
import os, sys
sys.path.insert(0, %r)
from PIL import Image, ImageDraw, ImageFont

def refuse(*args, **kwargs):
    raise AssertionError("a font file was asked for: %%r" %% (args,))

ImageFont.truetype = refuse
ImageFont.load_default = refuse
import neuronte_face as N
if not N.terminal_bundles():
    print("SKIP")
    raise SystemExit(0)
import theme as T

assert N.ONLY
# Every size and style is a Neuronte face, and none keeps another behind it.
for em in (1, 2, 8, 10, 11, 12, 16, 17, 24, 32, 33, 40, 64, 128, 256):
    for bold in (False, True):
        for italic in (False, True):
            font = T.font_at(em, bold=bold, italic=italic)
            assert isinstance(font, N.NeuronteFont), (em, bold, italic, font)
            assert font._fallback_font is None
            assert os.path.isfile(font.path) and font.path.endswith(".nrt")
            assert font.for_text("café 中") is font
            assert font.font_variant(font="DejaVuSans.ttf", size=em) is font

font = T.FONT
face = font._face
with face.lock:
    assert face.covers("Start") and not face.covers("→")
# A covered line measures and draws as it did.
plain = font.getlength("Start")
assert plain == sum(font.getlength(ch) for ch in "Start")
# An arrow split-v9 was trained on is its cell: one advance wider than the
# sum of the letters around it, and inked.
assert N.terminal_source(0x2192) == 0
arrow = font.getlength("a→b") - font.getlength("ab")
assert arrow == font.getlength("→") > 0
mask, offset = font.getmask2("→", "1")
assert offset == (0, 0) and mask.getbbox() is not None
# A character no bundle was trained on is the untrained mark: a hollow
# rectangle with a square in it, the same for any such character.
assert N.terminal_source(0x4E2D) == -1 and N.terminal_source(0xE0B0) == -1
one = font.getmask2("中", "1")[0]
two = font.getmask2("", "1")[0]
im1 = Image.new("1", one.size); im1.im.paste(one, (0, 0) + one.size)
im2 = Image.new("1", two.size); im2.im.paste(two, (0, 0) + two.size)
box = im1.getbbox()
assert box is not None
mark = im1.crop(box)
assert mark.tobytes() == im2.crop(im2.getbbox()).tobytes()
w, h = mark.size
assert all(mark.getpixel((x, 0)) and mark.getpixel((x, h - 1)) for x in range(w))
assert all(mark.getpixel((0, y)) and mark.getpixel((w - 1, y)) for y in range(h))
assert not mark.getpixel((1, 1))
# A letter and its combining mark are composed before they are looked up.
assert font.getlength("é") == font.getlength("é")
# Controls and joiners take no room.
assert font.getlength("a‍b\n") == font.getlength("ab")
# Bold, italic, the scaled and the large face draw the mixed line too, and
# the box is as wide as the measure.
canvas = Image.new("RGB", (1200, 200), (255, 255, 255))
draw = ImageDraw.Draw(canvas)
for em, bold, italic in ((11, True, False), (11, False, True), (20, False, False),
                         (20, True, True), (40, False, False), (40, True, False)):
    f = T.font_at(em, bold=bold, italic=italic)
    line = "← café 中 ✓"
    box = draw.textbbox((0, 0), line, font=f)
    assert box[2] - box[0] == f.getlength(line) > 0, (em, bold, italic)
    draw.text((2, 2), line, font=f, fill=(0, 0, 0))
    for anchor in ("la", "ls", "mm", "rs", "rb", "mt"):
        draw.text((600, 100), line, font=f, fill=(0, 0, 0), anchor=anchor)
assert canvas.getbbox() is not None
print("OK")
'''

env = dict(os.environ, KILIX_NEURONTE_ONLY="1")
done = subprocess.run([sys.executable, "-c", CHILD % HERE], env=env,
                      capture_output=True, text=True)
assert done.returncode == 0, done.stderr
assert done.stdout.strip() in ("OK", "SKIP"), done.stdout
print("test_neuronte_only:", done.stdout.strip())
