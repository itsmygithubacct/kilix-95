"""Neuronte desktop face for Kilix 95.

Binary weights through 32 px, and a blended scalable upright face above.
One weight file per small em: ``neuronte-ui{em}-v0.nrt``, and for italic
``neuronte-ui{em}-italic-v0.nrt``. Small bold is the letter struck twice,
one pixel to the right. Scalable bold dilates ink by round(em/32) pixels
and adds exactly that many pixels to each regular advance. A size or style with no file is
DejaVu (DejaVu Oblique for italic). A string with a character the file
does not cover is measured and drawn with DejaVu, so the two faces are
never mixed on one line.

``UI_TOP`` is the cell row where the em bitmap starts; the italic of an em
starts on the same row. It is read from the generated ``font/ui-tops.json``
table. The baseline row inside the em, and the baseline's cell row when
the drawing records one, are read from the face file's header.
A small face keeps one binary cell per character in memory, drawn once by
the net: a string is those cells laid at the pen. The cells are also kept
in the Kilix 95 cache, one file per em and slant, named by the bytes of the
weight file and of the library. A face that finds its file draws nothing
through the net. ``start_letters`` draws the set on a thread at a first
start, so the first frame does not wait for the net, and saves it.

anchor ``la`` puts the ascender on the pen: the mask is rows
``UI_TOP .. UI_TOP+em-1`` and the offset is ``(0, 0)``. Anchor ``ls`` uses
the same mask shifted up by the baseline row.
"""

import array
import ctypes
import hashlib
import json
import math
import os
import re
import stat
import struct
import threading
import tempfile
import time

from PIL import Image, ImageChops, ImageFont

# A Neuronte checkout (build/, weights/, font/, train/): NEURONTE_HOME, or
# else the installed one beside the other installed sources,
# $GPU_TERMINAL_SOURCE_HOME/neuronte (~/.local/gpu_terminal/sources/neuronte
# by default). Where it has no library or no weights for a size, that size
# keeps the theme's own DejaVu face.
def _installed_root():
    sources = (os.environ.get("GPU_TERMINAL_SOURCE_HOME")
               or "~/.local/gpu_terminal/sources")
    return os.path.join(os.path.abspath(os.path.expanduser(sources)), "neuronte")


_ROOT = os.environ.get("NEURONTE_HOME") or _installed_root()

_lib = None
_lib_failed = False
_lib_lock = threading.RLock()
_sizes = {}          # (em, italic) -> _Size or None
_sizes_lock = threading.Lock()
_tops = None


def _path(*parts):
    """A file in the Neuronte checkout, or "" if the root is empty."""
    return os.path.join(_ROOT, *parts) if _ROOT else ""


def _library():
    with _lib_lock:
        return _load_library()


def _load_library():
    global _lib, _lib_failed
    if _lib is not None or _lib_failed:
        return _lib
    path = os.environ.get("NEURONTE_LIB") or _path("build", "libneuronte.so")
    if not path:
        # ctypes.CDLL("") would open this process, not fail.
        _lib_failed = True
        return None
    try:
        lib = ctypes.CDLL(path)
        lib.neuronte_open_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        lib.neuronte_open_file.restype = ctypes.c_int
        lib.neuronte_set_binary.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.neuronte_set_binary.restype = ctypes.c_int
        lib.neuronte_text_width.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int]
        lib.neuronte_text_width.restype = ctypes.c_int
        lib.neuronte_draw_text.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32]
        lib.neuronte_draw_text.restype = ctypes.c_int
        # Older libraries still serve exact small faces. Scalable bold needs
        # both new entry points so its ink and measurements cannot disagree.
        try:
            width_stroke = lib.neuronte_text_width_stroke
            draw_stroke = lib.neuronte_draw_text_stroke
        except AttributeError:
            lib.has_stroke = False
        else:
            width_stroke.argtypes = lib.neuronte_text_width.argtypes
            width_stroke.restype = ctypes.c_int
            draw_stroke.argtypes = lib.neuronte_draw_text.argtypes
            draw_stroke.restype = ctypes.c_int
            lib.has_stroke = True
        lib.neuronte_advance_scalar.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        lib.neuronte_advance_scalar.restype = ctypes.c_uint32
        lib.neuronte_close.argtypes = [ctypes.c_void_p]
        lib.neuronte_close.restype = None
        _lib = lib
    except (OSError, AttributeError):
        _lib_failed = True
    return _lib


def _ui_tops():
    """Read generated placement data without importing or evaluating training code.

    An older checkout can still provide placement in each drawing's header.
    Missing or invalid metadata leaves those headers (or DejaVu) in control.
    """
    global _tops
    if _tops is not None:
        return _tops
    _tops = {}
    try:
        with open(_path("font", "ui-tops.json"), "rb") as fh:
            raw = fh.read(65537)
        if len(raw) > 65536:
            return _tops
        data = json.loads(raw)
        if data.get("schema") != "neuronte.ui-tops/v1":
            return _tops
        table = data["tops"]
        expected = {str(em) for em in range(1, 129) if em != 44}
        if not isinstance(table, dict) or table.keys() != expected:
            return _tops
        if not all(type(row) is int and 0 <= row <= 2 * int(em)
                   for em, row in table.items()):
            return _tops
        _tops = {int(em): row for em, row in table.items()}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return _tops


def _write_private(path, data):
    """Atomic 0600 write. A read-only or full cache is not an error."""
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                                   suffix=".tmp", dir=os.path.dirname(path))
        try:
            offset = 0
            while offset < len(data):
                count = os.write(fd, data[offset:])
                if count <= 0:
                    raise OSError("cache write made no progress")
                offset += count
        finally:
            os.close(fd)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read_private(path, limit):
    """Bytes of a regular file this user owns, at most limit, or None.

    A link is not followed, and a pipe is not waited for.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_size > limit):
            return None
        data = b""
        while len(data) <= limit:
            part = os.read(fd, limit + 1 - len(data))
            if not part:
                break
            data += part
        return data if len(data) <= limit else None
    except OSError:
        return None
    finally:
        os.close(fd)


def _face_path(em, italic):
    return _path("font",
                        "ui-%d%s.txt" % (em, "-italic" if italic else ""))


def _header(em, italic=False):
    """(baseline row inside the em, baseline cell row or None).

    The header is the comment lines before the first character. A sentence
    can wrap across them, so they are read as one text.
    """
    words = []
    try:
        with open(_face_path(em, italic), encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("# ") or line == "#":
                    words.append(line[2:])
                    continue
                break
    except OSError:
        return None, None
    text = " ".join(" ".join(words).split())
    found = re.search(r"The baseline is row (\d+)", text)
    baseline = int(found.group(1)) if found else None
    found = re.search(r"[Ii]n the drawn cell the baseline is row (\d+)", text)
    cell = int(found.group(1)) if found else None
    return baseline, cell


class _Size:
    def __init__(self, em, ptr, ui_top, baseline, rows=None, scalable=False,
                 italic=False):
        self.em = em
        self.rows = em if rows is None else rows
        self.scalable = scalable
        self.ptr = ptr
        self.ui_top = ui_top
        self.baseline = baseline
        self.lock = threading.RLock()
        self._cover = {}
        self.letters = None if scalable else _Letters(self, italic)

    def covers(self, text):
        # Caller holds self.lock. The handle is not safe to share unlocked.
        for ch in text:
            cp = ord(ch)
            hit = self._cover.get(cp)
            if hit is None:
                hit = _lib.neuronte_advance_scalar(self.ptr, cp) == cp
                self._cover[cp] = hit
            if not hit:
                return False
        return True

    def width(self, text, bold):
        data = text.encode("utf-8")
        if self.scalable and bold:
            return _lib.neuronte_text_width_stroke(
                self.ptr, data, len(data), self.stroke(bold), self.em)
        return _lib.neuronte_text_width(self.ptr, data, len(data), bold, self.em)

    def stroke(self, bold):
        return max(1, (self.em + 16) // 32) if self.scalable and bold else int(bool(bold))


def open_size(em, italic=False):
    """The face for this em, upright or italic, or None when the weight,
    the crop, or the baseline is missing. A later size is another file,
    not a code change."""
    key = (int(em), bool(italic))
    with _sizes_lock:
        if key in _sizes:
            return _sizes[key]
        loaded = _load(*key)
        _sizes[key] = loaded
        return loaded


def weight_path(em, italic=False):
    if int(em) >= 33 and not italic:
        return _path("weights", "neuronte-ui-large-v0.nrt")
    return _path("weights", "neuronte-ui%d%s-v0.nrt"
                        % (int(em), "-italic" if italic else ""))


def _load(em, italic=False):
    lib = _library()
    if lib is None:
        return None
    path = weight_path(em, italic)
    if not os.path.isfile(path):
        return None
    scalable = em >= 33 and not italic
    if scalable:
        # Geometry from glyphs.large_rows; checked against that source in tests.
        ui_top = math.floor(0.6 * em)
        rows = math.ceil(1.6 * em) - ui_top
        baseline = math.floor((1.35 + 3 / 64) * em - 0.5) - ui_top
    else:
        tops = _ui_tops()
        baseline, cell = _header(em, italic)
        ui_top = tops.get(em)
        if ui_top is None and baseline is not None and cell is not None:
            ui_top = cell - baseline
        if ui_top is None or baseline is None:
            return None
        if cell is not None and cell - baseline != ui_top:
            return None
        rows = em
    if not 0 <= baseline < rows or ui_top < 0:
        return None
    handle = ctypes.c_void_p()
    if lib.neuronte_open_file(path.encode(), ctypes.byref(handle)) != 0:
        return None
    if lib.neuronte_set_binary(handle, 0 if scalable else 1) != 0:
        lib.neuronte_close(handle)
        return None
    return _Size(em, handle, ui_top, baseline, rows, scalable, italic)


def _as_text(text):
    if isinstance(text, bytes):
        return text.decode("utf-8", "replace")
    return str(text)


def _mask(size, text, bold, mode):
    """Em-tall mask of the face. Rows are UI_TOP .. UI_TOP+em-1.

    Caller holds size.lock.
    """
    if size.scalable:
        mode = "L"
    data = text.encode("utf-8")
    width = size.width(text, bold)
    if width < 0:
        return None
    if mode == "1" and width > 0 and size.letters is not None:
        im = size.letters.mask(text, bold, width)
        if im is not None:
            return im.im
    if width == 0:
        im = Image.new("1" if mode == "1" else "L", (1, max(1, size.rows)), 0)
        return im.im
    buf_w = width + size.em + 2
    buf_h = size.rows
    buf = (ctypes.c_uint32 * (buf_w * buf_h))()
    draw = _lib.neuronte_draw_text_stroke if size.scalable and bold else _lib.neuronte_draw_text
    rc = draw(
        size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
        0, -size.ui_top, size.em, size.stroke(bold), data, len(data), 0xFFFFFFFF)
    if rc < 0:
        return None
    if mode == "1":
        im = _pack_binary(buf, buf_w, buf_h)
    else:
        raw = array.array("B", (px >> 24 for px in buf))
        im = Image.frombytes("L", (buf_w, buf_h), raw.tobytes())
    return im.im


_NONZERO = [0] + [255] * 255


def _pack_binary(buf, buf_w, buf_h):
    """Mode "1" image with a bit set wherever the 32-bit pixel is not zero.

    Pillow merges the four channels by maximum and cuts at one; a Python
    loop over the pixels took 25 times as long as the drawing itself.
    """
    rgba = Image.frombuffer("RGBA", (buf_w, buf_h), buf, "raw", "RGBA", 0, 1)
    c0, c1, c2, c3 = rgba.split()
    any_ink = ImageChops.lighter(ImageChops.lighter(c0, c1), ImageChops.lighter(c2, c3))
    return any_ink.point(_NONZERO, "1")


# What the small faces cover, most used first: printable ASCII and the
# ellipsis. start_letters draws these ahead of need.
COMMON = ("etaoinsrhldcumfpgwybvkxjqz ETAOINSRHLDCUMFPGWYBVKXJQZ"
          "0123456789.:,-_/()'\"&!?+*=%#@;<>[]{}|\\~^`$\u2026")


# The cells of one small face on disk. After the magic, each cell is its
# scalar, advance, bold advance and width, then ceil(width / 8) * rows
# bytes of a Pillow mode "1" image; a sha256 of all the cells ends the file.
# The name is a sha256 over the weight file's and the library's own sha256,
# this format number, and the em, slant, rows and UI_TOP the cells were drawn
# with: other weights or another library never find this file. Nothing is
# deleted or migrated; a file that fails any check is not used.
_CELLS_FORMAT = 1
_CELLS_MAGIC = b"NRTATLAS"
_CELLS_LIMIT = 1 << 20
_CELL = struct.Struct("<IHHH")
_ADVANCE_LIMIT = 4096
_digests = {}        # library path -> sha256 of its bytes


def _file_digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).digest()


def _cells_path(size, italic):
    """Where this face's cells are kept, or "" when they cannot be."""
    library = getattr(_lib, "_name", "")
    try:
        weights = _file_digest(weight_path(size.em, italic))
        code = _digests.get(library)
        if code is None:
            code = _digests[library] = _file_digest(library)
        import storage
        folder = storage.private_dir(storage.cache_dir("neuronte"))
    except Exception:
        return ""
    name = hashlib.sha256(weights + code + b"%d %d %d %d %d" % (
        _CELLS_FORMAT, size.em, int(bool(italic)), size.rows, size.ui_top))
    return os.path.join(folder, "cells-%s.bin" % name.hexdigest())


def _pack_cells(cells):
    body = bytearray()
    for cp, (adv, badv, width, im) in sorted(cells.items()):
        body += _CELL.pack(cp, adv, badv, width)
        if width:
            body += im.tobytes()
    return _CELLS_MAGIC + bytes(body) + hashlib.sha256(body).digest()


def _read_cells(path, em, rows):
    """{scalar: cell} from a cells file, or None when any part is wrong."""
    raw = _read_private(path, _CELLS_LIMIT) if path else None
    if raw is None or raw[:8] != _CELLS_MAGIC:
        return None
    body, digest = raw[8:-32], raw[-32:]
    if hashlib.sha256(body).digest() != digest:
        return None
    pos, cells = 0, {}
    while pos < len(body):
        if pos + _CELL.size > len(body):
            return None
        cp, adv, badv, width = _CELL.unpack_from(body, pos)
        pos += _CELL.size
        # A cell is never wider than the buffer it was cut from.
        if (cp > 0x10FFFF or cp in cells or adv > _ADVANCE_LIMIT
                or badv > _ADVANCE_LIMIT or width > adv + em + 2):
            return None
        count = (width + 7) // 8 * rows
        if pos + count > len(body):
            return None
        im = Image.frombytes("1", (width, rows), body[pos:pos + count]) if width else None
        pos += count
        cells[cp] = (adv, badv, width, im)
    return cells


class _Letters:
    """Binary cells of one small face, one per character, kept in memory.

    A cell is the face's own drawing of that character alone, cut after its
    last inked column. A string is the cells laid at the pen and merged,
    which is what the library does in binary mode: a pixel is set when any
    letter sets it. Bold lays each cell twice, one pixel apart, and steps
    by the bold advance. The net draws each character once per process, and
    not at all when the face's cells file holds it. Bold uses the regular
    cells, so one file serves both. The owner holds ``size.lock`` around
    every call.
    """

    def __init__(self, size, italic=False):
        self.size = size
        self.unsaved = False   # a cell was drawn here that the file does not hold
        self.path = _cells_path(size, italic)
        # scalar -> (advance, bold advance, width, image or None)
        self.cells = _read_cells(self.path, size.em, size.rows) or {}

    def complete(self):
        return all(ord(ch) in self.cells for ch in COMMON)

    def save(self):
        """Write the cells if any is new. A failed write is ignored."""
        if self.unsaved and self.path and _write_private(self.path, _pack_cells(self.cells)):
            self.unsaved = False

    def cell(self, ch):
        hit = self.cells.get(ord(ch))
        if hit is not None:
            return hit
        size = self.size
        data = ch.encode("utf-8")
        adv = _lib.neuronte_text_width(size.ptr, data, len(data), 0, size.em)
        badv = _lib.neuronte_text_width(size.ptr, data, len(data), 1, size.em)
        if adv < 0 or badv < 0:
            return None
        buf_w, buf_h = adv + size.em + 2, size.rows
        buf = (ctypes.c_uint32 * (buf_w * buf_h))()
        if _lib.neuronte_draw_text(
                size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
                0, -size.ui_top, size.em, 0, data, len(data), 0xFFFFFFFF) < 0:
            return None
        im = _pack_binary(buf, buf_w, buf_h)
        box = im.getbbox()
        if box is None:
            hit = (adv, badv, 0, None)
        else:
            # Columns 0 .. last inked; the left edge stays at the pen.
            hit = (adv, badv, box[2], im.crop((0, 0, box[2], buf_h)))
        self.cells[ord(ch)] = hit
        self.unsaved = True
        return hit

    def mask(self, text, bold, width):
        """The string's mask, or None so the caller asks the library."""
        size = self.size
        out = Image.new("1", (width + size.em + 2, size.rows), 0)
        pen = 0
        for ch in text:
            hit = self.cell(ch)
            if hit is None:
                return None
            adv, badv, w, im = hit
            if w:
                out.paste(1, (pen, 0), im)
                if bold:
                    out.paste(1, (pen + 1, 0), im)
            pen += badv if bold else adv
        if pen != width:
            return None
        return out


def _draw_letters(sizes):
    for size in sizes:
        for ch in COMMON:
            with size.lock:
                size.letters.cell(ch)
            # A Python lock is not fair: taking it again at once kept the
            # desktop waiting about 55 ms in set-up. A short sleep outside
            # the lock lets a waiter in.
            time.sleep(0.0002)
        with size.lock:
            size.letters.save()


def save_letters():
    """Save every small face whose cells grew since they were read.

    For the end of a run: a size opened after start has no thread to save it.
    """
    for size in list(_sizes.values()):
        if size is not None and size.letters is not None:
            with size.lock:
                size.letters.save()


def start_letters(fonts):
    """Draw the common characters of these fonts' small faces on a thread,
    then save them.

    Returns the thread, or None when there is nothing to draw: a face whose
    cells file was read is complete already. The desktop does not wait for
    it: a character it has not reached is drawn when asked for, under the
    same lock.
    """
    seen, sizes = set(), []
    for font in fonts:
        face = getattr(font, "_face", None)
        if face is None or face.letters is None or id(face) in seen:
            continue
        seen.add(id(face))
        with face.lock:
            if not face.letters.complete():
                sizes.append(face)
    if not sizes:
        return None
    thread = threading.Thread(target=_draw_letters, args=(sizes,),
                              name="neuronte-letters", daemon=True)
    thread.start()
    return thread


class NeuronteFont:
    """A PIL font that draws with the face and keeps a real TTF path.

    ``path`` is the DejaVu file a caller can reopen (the oblique one for an
    italic face). This object is not a
    FreeTypeFont, so a worker that refuses to share a FreeType face will
    share this one. The face handle, and the fallback face, are locked.
    """

    def __init__(self, size, bold, path, face, fallback, variant, italic=False):
        self.size = int(size)
        self.bold = 1 if bold else 0
        self.italic = bool(italic)
        self.path = path
        self._face = face
        self._fallback_font = fallback
        self._variant = variant
        # A width here is the sum of each character's own rounded advance.
        self.additive = True

    def _use_face(self, text, direction=None, features=None, language=None, stroke_width=0):
        # This adapter lays out independent supported scalars only. Let the
        # shaped fallback handle a whole request when it asks for a layout
        # feature or outline this renderer cannot honor.
        if (direction is not None or features is not None or language is not None
                or stroke_width):
            return False
        if not self._face.covers(text):
            return False
        return self._face.width(text, self.bold) >= 0

    def for_text(self, text):
        """Select one font for a consumer that later measures substrings.

        Keep this selection for a whole styled run, including its metrics,
        selection redraw and caret prefixes. A supported prefix of an
        unsupported run must not switch back to neural advances.
        """
        with self._face.lock:
            return self if self._use_face(_as_text(text)) else self._fallback_font

    def _offset(self, anchor):
        if anchor in (None, "la", "lt"):
            return (0, 0)
        if anchor == "ls":
            return (0, -self._face.baseline)
        return None

    def getlength(self, text, mode="", direction=None, features=None,
                  language=None):
        s = _as_text(text)
        with self._face.lock:
            if not self._use_face(s, direction, features, language):
                return self._fallback_font.getlength(
                    s, mode, direction, features, language)
            return self._face.width(s, self.bold)

    def getbbox(self, text, mode="", direction=None, features=None,
                language=None, stroke_width=0, anchor=None):
        s = _as_text(text)
        off = self._offset(anchor)
        with self._face.lock:
            if off is None or not self._use_face(s, direction, features, language, stroke_width):
                return self._fallback_font.getbbox(
                    s, mode, direction, features, language, stroke_width, anchor)
            width = self._face.width(s, self.bold)
        left, top = off
        stroke = int(stroke_width or 0)
        return (left, top - stroke, left + width + 2 * stroke,
                top + self._face.rows + stroke)

    def getmetrics(self):
        # This Pillow reports descent as a positive distance below the baseline.
        above = self._face.baseline
        below = self._face.rows - self._face.baseline - 1
        return above, max(0, below)

    def getmask(self, text, mode="", *args, **kwargs):
        return self.getmask2(text, mode, *args, **kwargs)[0]

    def getmask2(self, text, mode="", direction=None, features=None,
                 language=None, stroke_width=0, anchor=None, ink=0,
                 start=None, *args, **kwargs):
        s = _as_text(text)
        off = self._offset(anchor)
        with self._face.lock:
            if off is None or not self._use_face(s, direction, features, language, stroke_width):
                return self._fallback_font.getmask2(
                    s, mode, direction, features, language, stroke_width,
                    anchor, ink, start, *args, **kwargs)
            mask = _mask(self._face, s, self.bold, mode)
            if mask is None:
                return self._fallback_font.getmask2(
                    s, mode, direction, features, language, stroke_width,
                    anchor, ink, start, *args, **kwargs)
        return mask, off

    def font_variant(self, font=None, size=None, index=None, encoding=None,
                     layout_engine=None):
        if font is not None:
            return self._fallback_font.font_variant(
                font=font, size=size, index=index, encoding=encoding,
                layout_engine=layout_engine)
        new = self.size if size is None else int(round(float(size)))
        return self._variant(new, bold=bool(self.bold), italic=self.italic)


def try_font(size, bold, fallback, variant, italic=False):
    """A NeuronteFont for this size and style, or None so the caller keeps
    DejaVu. ``fallback`` is the DejaVu face of the same style."""
    path = getattr(fallback, "path", None)
    if not isinstance(path, (str, bytes, os.PathLike)) or not os.path.isfile(path):
        return None
    if not isinstance(fallback, ImageFont.FreeTypeFont):
        return None
    face = open_size(size, italic)
    if face is None:
        return None
    if face.scalable and bold and not _lib.has_stroke:
        return None
    return NeuronteFont(size, bold, path, face, fallback, variant, italic)
