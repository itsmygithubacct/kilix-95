"""Start-up shortcuts of the Neuronte face give what the long way gives.

The letter cells in memory, the Pillow mask packing, the cached UI_TOP
table and the clock width from parts each replace slower code. Each is
compared here with that slower code, bit for bit or number for number.
"""
import ctypes
import os
import random
import time

import harness as H  # noqa: F401  (isolated storage before the desktop imports)
from PIL import Image
import neuronte_face as N
import theme as T
from neuronte_face_check import require

require(all(N.open_size(em) for em in (10, 11)), "no Neuronte 10px or 11px weights")


def library_mask(size, text, bold):
    """The string drawn by the library in one call, packed by a pixel loop."""
    data = text.encode("utf-8")
    width = size.width(text, bold)
    buf_w, buf_h = width + size.em + 2, size.rows
    buf = (ctypes.c_uint32 * (buf_w * buf_h))()
    assert N._lib.neuronte_draw_text(
        size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
        0, -size.ui_top, size.em, int(bool(bold)), data, len(data), 0xFFFFFFFF) >= 0
    row_b = (buf_w + 7) // 8
    packed = bytearray(row_b * buf_h)
    for i, px in enumerate(buf):
        if px:
            y, x = divmod(i, buf_w)
            packed[y * row_b + (x >> 3)] |= 0x80 >> (x & 7)
    return (buf_w, buf_h), bytes(packed), buf


def raw(core):
    im = Image.new("1", core.size)
    im.im = core
    return im.size, im.tobytes()


rng = random.Random(95)
letters = [chr(c) for c in range(32, 127)] + ["…"]
corpus = ["Start", "My Computer", "12:08 AM", "WAVE AWAY fjord_Typ.{}[]|\\~^`$",
          "…", "a", "ff ij ll WW //", "budget 2026.txt"]
corpus += ["".join(rng.choice(letters) for _ in range(rng.randint(1, 40)))
           for _ in range(150)]

for em in (10, 11):
    size = N.open_size(em)
    # COMMON is exactly what the face covers, so the start-up thread draws
    # every letter the face can be asked for and nothing it cannot.
    covered = {chr(cp) for cp in range(0x3000)
               if N._lib.neuronte_advance_scalar(size.ptr, cp) == cp}
    assert covered == set(N.COMMON), (em, covered ^ set(N.COMMON))
    assert len(N.COMMON) == len(set(N.COMMON))
    for bold in (0, 1):
        for text in corpus:
            with size.lock:
                want_size, want, buf = library_mask(size, text, bold)
                width = size.width(text, bold)
                # The cells themselves made it: not the library fallback.
                cells = size.letters.mask(text, bold, width)
                assert cells is not None, (em, bold, text)
                assert (cells.size, cells.tobytes()) == (want_size, want), (em, bold, text)
                assert raw(N._mask(size, text, bold, "1")) == (want_size, want)
                packed = N._pack_binary(buf, *want_size)
                assert (packed.size, packed.tobytes()) == (want_size, want)

# The start-up thread fills every cell of both faces and ends.
thread = N.start_letters((T.FONT, T.BOLD, T.SMALL))
if thread is not None:
    thread.join(60)
    assert not thread.is_alive()
for font in (T.FONT, T.SMALL):
    assert {ord(ch) for ch in N.COMMON} <= set(font._face.letters.cells)
# FONT and BOLD share one face: it is drawn once.
assert T.FONT._face is T.BOLD._face
# A scalable face keeps the library path.
big = N.open_size(64)
assert big is None or big.letters is None

# Clock: the width from parts is the widest of all 1,440 stamps.
assert isinstance(T.FONT, N.NeuronteFont) and T.FONT.additive
full = max(T.text_w(T.FONT, time.strftime("%I:%M %p", T._clock_stamp(h, m)))
           for h in range(24) for m in range(60))
T._CLOCK_WIDEST.clear()
assert T._widest_clock() == full
assert T.CLOCK_W == T._CLOCK_LEFT + full + T._CLOCK_RIGHT
# A face that does not add up measures every stamp.
fallback = T.FONT._fallback_font
saved = T.FONT
try:
    T.FONT = fallback
    T._CLOCK_WIDEST.clear()
    assert T._widest_clock() == max(
        T.text_w(fallback, time.strftime("%I:%M %p", T._clock_stamp(h, m)))
        for h in range(24) for m in range(60))
finally:
    T.FONT = saved
    T._CLOCK_WIDEST.clear()

# UI_TOP: the cached table is the evaluated one; a damaged file is not read.
source = open(N._path("train", "glyphs.py"), encoding="utf-8").read()
evaluated = N._eval_tops(source, "glyphs.py")
path = N._tops_cache_path(source)
assert path and os.path.isfile(path), "the table was not cached at import"
assert N._read_tops(path) == evaluated == N._ui_tops()
assert os.stat(path).st_mode & 0o777 == 0o600
assert N._tops_cache_path(source + "\n# edited\n") != path
good = open(path, "rb").read()
for bad in (b"", b"{", b"[1, 2]", b'{"11": "x"}', b'{"11": -1}', b'{"0": 3}', b"{}"):
    with open(path, "wb") as fh:
        fh.write(bad)
    assert N._read_tops(path) is None, bad
    N._tops = None
    assert N._ui_tops() == evaluated          # falls back to the source
    assert N._read_tops(path) == evaluated    # and repairs the file
with open(path, "wb") as fh:
    fh.write(good)
link = path + ".link"
os.symlink(path, link)
try:
    assert N._read_tops(link) is None         # a link is never followed
finally:
    os.unlink(link)
print("ok")
