"""Optional flame artwork from its own palette-bearing Neuronte file."""
import ctypes
import os
import threading

from PIL import Image
import neuronte_face

_lock = threading.RLock()
_handle = None
_failed = False


def image(size):
    """Straight-alpha RGBA, or None so the caller retains its drawn icon."""
    global _handle, _failed
    if size not in (16, 32):
        return None
    with _lock:
        if _failed:
            return None
        lib = neuronte_face._library()
        if lib is None:
            return None
        if _handle is None:
            path = neuronte_face._path("weights", "neuronte-flame-v0.nrt")
            handle = ctypes.c_void_p()
            if lib.neuronte_open_file(path.encode(), ctypes.byref(handle)) != 0:
                _failed = True
                return None
            lib.neuronte_draw_scalar.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint32, ctypes.c_uint32]
            lib.neuronte_draw_scalar.restype = ctypes.c_int
            _handle = handle
        pixels = (ctypes.c_uint32 * (size * size))()
        if lib.neuronte_draw_scalar(_handle, pixels, size, size, size,
                                    0, -size // 2, size, 2 * size,
                                    0x100000, 0xFFFFFFFF) != 0:
            return None
        # The library composites layers before blending and returns straight
        # AARRGGBB, including on transparent destinations. Do not unpremultiply
        # a second time or independently blend rounded layer images.
        rgba = bytes(channel for px in pixels
                     for channel in ((px >> 16) & 255, (px >> 8) & 255,
                                     px & 255, px >> 24))
        return Image.frombytes("RGBA", (size, size), rgba)
