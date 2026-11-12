"""Flame crop, palette/alpha and fallback through the icon consumer."""
import ctypes
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import harness as H
from PIL import Image
import icons
import neuronte_flame as F
import neuronte_face as N
from neuronte_face_check import require

require(N._library() is not None and os.path.isfile(N._path('weights', 'neuronte-flame-v0.nrt')),
        'no Neuronte library or flame weights')

for size in (16, 32):
    actual = icons.get('flame', size)
    assert F._handle is not None, 'real flame asset is required for this integration test'
    lib = N._library()
    full = (ctypes.c_uint32 * (2 * size * size))()
    assert lib.neuronte_draw_scalar(F._handle, full, size, size, 2*size,
                                    0, 0, size, 2*size, 0x100000, 0xFFFFFFFF) == 0
    crop = full[size*size//2:3*size*size//2]
    assert actual.tobytes() == bytes(c for p in crop for c in
                                    ((p>>16)&255, (p>>8)&255, p&255, p>>24))
    assert any(0 < a < 255 for a in actual.getchannel('A').getdata())
    # Compare compositing over both real desktop surfaces to the C library.
    for bg in (0xFFC0C0C0, 0xFF008080):
        dest = (ctypes.c_uint32 * (size*size))(*([bg]*(size*size)))
        assert lib.neuronte_draw_scalar(F._handle, dest, size, size, size,
                                        0, -size//2, size, 2*size, 0x100000, 0xFFFFFFFF) == 0
        canvas = Image.new('RGB', (size,size), ((bg>>16)&255,(bg>>8)&255,bg&255))
        icons.paint(canvas, 'flame', 0, 0, size)
        expected = bytes(c for p in dest for c in ((p>>16)&255,(p>>8)&255,p&255))
        assert max(abs(a-b) for a,b in zip(canvas.tobytes(), expected)) <= 1
    assert icons.get('flame',size) is actual
    assert icons.get('flame',size,True).tobytes() != actual.tobytes()
with ThreadPoolExecutor(max_workers=4) as pool:
    assert len(set(pool.map(lambda _: F.image(16).tobytes(), range(8)))) == 1
assert F.image(24) is None
with patch.object(F, '_handle', None), patch.object(F, '_failed', False), patch.object(N, '_ROOT', '/nonexistent-neuronte-test'):
    assert F.image(16) is None
with patch.object(F, 'image', return_value=None):
    icons._cache.clear()
    for size in (16,32,24):
        art = icons.P(max(1,size//16)); icons._flame(art)
        expected = art.img.resize((size,size), Image.Resampling.NEAREST)
        assert icons.get('flame',size).tobytes() == expected.tobytes()
print('ok')
