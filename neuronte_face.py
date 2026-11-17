"""Neuronte desktop face for Kilix 95.

Binary weights through 32 px, and a blended scalable upright face above.
One weight file per small em: ``neuronte-ui{em}-v1.nrt``, and for italic
``neuronte-ui{em}-italic-v1.nrt``; a tree that has only the earlier ``-v0``
files is read the same way. A tree with no file for an em from 17 to 32
but with ``neuronte-ui-scaled-v0.nrt``, or the ``-latin1`` file that adds
the accented letters, draws that em with it: one design
scaled, its stems snapped to whole pixels by the library, binary like the
small faces and kept letter by letter the same way. Its italic is the
upright letter sheared by the library and stepped by
``neuronte-ui-scaled-italic-advances-v0.nrt``. Small bold is the letter struck twice,
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

``KILIX_NEURONTE_ONLY=1`` turns the DejaVu fallback off: no font file is
opened at all. Every size and style is drawn by a Neuronte face (a size or
slant with no file of its own takes the nearest that has one), and a
character the face does not cover is drawn, in a terminal cell set on the
line, by the first terminal bundle trained on it
(``neuronte-split-v9.nrt``, then each ``neuronte-term-*.nrt``). A character
none of them was trained on shows the library's own untrained mark.
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
import unicodedata

from PIL import Image, ImageChops, ImageFont

# No font file at all: see the module text. Read once, at import.
ONLY = os.environ.get("KILIX_NEURONTE_ONLY") == "1"

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
        # The library's own packing and line laying, where it has them; an
        # earlier library leaves that work to the Pillow code below.
        try:
            pack, alpha, compose = (lib.neuronte_bits_pack, lib.neuronte_alpha_pack,
                                    lib.neuronte_bits_compose)
        except AttributeError:
            lib.has_bits = False
        else:
            pack.argtypes = alpha.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_void_p, ctypes.c_size_t]
            compose.argtypes = [
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
            pack.restype = alpha.restype = compose.restype = ctypes.c_int
            lib.has_bits = True
        lib.neuronte_advance_scalar.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        lib.neuronte_advance_scalar.restype = ctypes.c_uint32
        # The scaled face's italic: a sheared letter and its own advances.
        try:
            styled = lib.neuronte_draw_scalar_styled
            advance = lib.neuronte_advance
        except AttributeError:
            lib.has_styled = False
        else:
            styled.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint]
            styled.restype = ctypes.c_int
            advance.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int]
            advance.restype = ctypes.c_int
            lib.has_styled = True
        lib.neuronte_close.argtypes = [ctypes.c_void_p]
        lib.neuronte_close.restype = None
        # What a terminal bundle was trained on, its untrained mark, and a
        # cell's plain coverage: the characters a face does not cover.
        try:
            untrained, set_untrained = lib.neuronte_untrained, lib.neuronte_set_untrained
        except AttributeError:
            lib.has_untrained = False
        else:
            untrained.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            untrained.restype = ctypes.c_int
            set_untrained.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_untrained.restype = ctypes.c_int
            lib.neuronte_coverage.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_void_p]
            lib.neuronte_coverage.restype = ctypes.c_int
            lib.has_untrained = True
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
                 italic=False, slant=None):
        self.em = em
        # The advances of a sheared italic, when the letters are the upright
        # face's: the scaled face from 17 to 32 px. None for every other face.
        self.slant = slant
        self.rows = em if rows is None else rows
        self.scalable = scalable
        self.ptr = ptr
        self.ui_top = ui_top
        self.baseline = baseline
        self.lock = threading.RLock()
        self._cover = {}
        self._extra = {}     # scalar -> cell from a terminal bundle (ONLY)
        self._extra_at = None
        self.letters = None if scalable else _Letters(self, italic)

    def covered(self, ch):
        # Caller holds self.lock.
        cp = ord(ch)
        hit = self._cover.get(cp)
        if hit is None:
            hit = self._cover[cp] = _lib.neuronte_advance_scalar(self.ptr, cp) == cp
        return hit

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
        if ONLY and not self.covers(text):
            return self.mixed_width(text, bold)
        data = text.encode("utf-8")
        if self.scalable and bold:
            return _lib.neuronte_text_width_stroke(
                self.ptr, data, len(data), self.stroke(bold), self.em)
        return _lib.neuronte_text_width(self.slant or self.ptr, data, len(data), bold, self.em)

    def stroke(self, bold):
        return max(1, (self.em + 16) // 32) if self.scalable and bold else int(bool(bold))

    # The rest is for ONLY: a line with characters the face does not cover.

    def runs(self, text):
        """The text as (covered, string) pieces: a covered piece is a run the
        face draws, any other is one character."""
        out, run = [], ""
        for ch in text:
            if self.covered(ch):
                run += ch
                continue
            if run:
                out.append((True, run))
                run = ""
            out.append((False, ch))
        if run:
            out.append((True, run))
        return out

    def extra(self, ch):
        """(advance, bold advance, width, binary image or None, grey image or
        None) of a character the face does not cover, on this face's rows."""
        hit = self._extra.get(ord(ch))
        if hit is None:
            hit = self._extra[ord(ch)] = _extra_cell(self, ch)
        return hit

    def mixed_width(self, text, bold):
        total = 0
        for covered, piece in self.runs(text):
            if covered:
                data = piece.encode("utf-8")
                if self.scalable and bold:
                    part = _lib.neuronte_text_width_stroke(
                        self.ptr, data, len(data), self.stroke(bold), self.em)
                else:
                    part = _lib.neuronte_text_width(
                        self.slant or self.ptr, data, len(data), bold, self.em)
                if part < 0:
                    return part
                total += part
            else:
                cell = self.extra(piece)
                total += cell[1] if bold else cell[0]
        return total


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


def newest(stem, versions):
    """The weight file of the first of these versions that is present, or
    the first one's path when none is. A tree holds one generation of a
    net: the slim Neuronte set has the later one, an older tree the earlier."""
    paths = [_path("weights", "%s-v%d.nrt" % (stem, v)) for v in versions]
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return paths[0]


SCALED = range(17, 33)     # the ems one scaled file can draw


def _first(*names):
    """The first of these weight files that is present, or the first's path."""
    paths = [_path("weights", name) for name in names]
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return paths[0]


def _scaled_path():
    # The file with the Latin-1 letters where a tree has it: the same ASCII.
    return _first("neuronte-ui-scaled-latin1-v0.nrt", "neuronte-ui-scaled-v0.nrt")


def _slant_path():
    if os.path.basename(_scaled_path()) == "neuronte-ui-scaled-latin1-v0.nrt":
        return _path("weights", "neuronte-ui-scaled-latin1-italic-advances-v0.nrt")
    return _path("weights", "neuronte-ui-scaled-italic-advances-v0.nrt")


def weight_path(em, italic=False):
    if int(em) >= 33 and not italic:
        return _first("neuronte-ui-large-latin1-v1.nrt", "neuronte-ui-large-v1.nrt",
                      "neuronte-ui-large-v0.nrt")
    own = newest("neuronte-ui%d%s" % (int(em), "-italic" if italic else ""),
                 (1, 0))
    if int(em) in SCALED and not os.path.isfile(own):
        scaled = _scaled_path()
        if scaled and os.path.isfile(scaled) and (
                not italic or os.path.isfile(_slant_path())):
            return scaled
    return own


def kind(em, italic=False):
    """How this em is drawn: "pixel" by its own hand-drawn face, "scaled"
    by the one scaled face, "large" by the blended face above 32 px, or
    None when no file draws it."""
    path = weight_path(em, italic)
    if not path or not os.path.isfile(path):
        return None
    if int(em) >= 33 and not italic:
        return "large"
    return "scaled" if path == _scaled_path() else "pixel"


def _load(em, italic=False):
    lib = _library()
    if lib is None:
        return None
    path = weight_path(em, italic)
    if not os.path.isfile(path):
        return None
    scalable = em >= 33 and not italic
    scaled = not scalable and path == _scaled_path()
    if scaled and italic and not lib.has_styled:
        return None
    if scalable or scaled:
        # Geometry from glyphs.large_rows; checked against that source in tests.
        # The scaled face is the same design in the same cell.
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
    slant = None
    if scaled and italic:
        slant = ctypes.c_void_p()
        if lib.neuronte_open_file(_slant_path().encode(), ctypes.byref(slant)) != 0:
            lib.neuronte_close(handle)
            return None
    return _Size(em, handle, ui_top, baseline, rows, scalable, italic, slant)


def _as_text(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = str(text)
    if ONLY and not text.isascii():
        # A letter and its mark become the one character a bundle may hold.
        text = unicodedata.normalize("NFC", text)
    return text


_terminal = None     # [handle, ...]: split-v9 first, then each term bundle
_terminal_lock = threading.RLock()

# Characters that take no room and have no picture: controls, joiners,
# variation selectors, the byte order mark.
_NO_PICTURE = (set(range(0x20)) | set(range(0x7F, 0xA0))
               | {0xAD, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF}
               | set(range(0xFE00, 0xFE10)))


def terminal_bundles():
    """The terminal bundles of this tree, in the order they are asked."""
    names = []
    try:
        listed = sorted(os.listdir(_path("weights")))
    except OSError:
        listed = []
    for version in range(20, 6, -1):
        name = "neuronte-split-v%d.nrt" % version
        if name in listed:
            names.append(name)
            break
    names += [n for n in listed if re.fullmatch(r"neuronte-term-[a-z0-9-]+-v\d+\.nrt", n)]
    return [_path("weights", n) for n in names]


def _terminal_handles():
    # Caller holds _terminal_lock.
    global _terminal
    if _terminal is None:
        _terminal = []
        lib = _library()
        if lib is not None and lib.has_untrained:
            for path in terminal_bundles():
                handle = ctypes.c_void_p()
                if lib.neuronte_open_file(path.encode(), ctypes.byref(handle)) != 0:
                    continue
                if not _terminal:
                    # The first bundle draws the mark for what none has.
                    lib.neuronte_set_untrained(handle, 1)
                _terminal.append(handle)
    return _terminal


def terminal_source(cp):
    """Which terminal bundle draws this scalar: its index, or -1 when none
    was trained on it and the first one's untrained mark stands for it."""
    with _terminal_lock:
        for index, handle in enumerate(_terminal_handles()):
            if _lib.neuronte_untrained(handle, cp) == 0:
                return index
    return -1


def _terminal_cell(cp, cell_w, cell_h):
    """Coverage of a terminal cell as a mode "L" image, or None."""
    with _terminal_lock:
        handles = _terminal_handles()
        if not handles:
            return None
        handle = handles[0]
        for other in handles[1:]:
            if _lib.neuronte_untrained(other, cp) == 0:
                handle = other
                break
        buf = (ctypes.c_float * (cell_w * cell_h))()
        if _lib.neuronte_coverage(handle, cp, cell_w, cell_h, 0, buf) != 0:
            return None
    raw = bytes(min(255, max(0, int(v * 255.0 + 0.5))) for v in buf)
    return Image.frombytes("L", (cell_w, cell_h), raw)


def _ink_bottom(im):
    box = im.point(lambda v: 255 if v >= 128 else 0).getbbox() if im is not None else None
    return None if box is None else box[3] - 1


def _extra_geometry(size):
    """(cell width, cell height, row of the cell's top on this face's rows).

    The terminal cell is 1 wide and 2 high and its capitals are 0.55 of its
    height; 0.65 em wide puts them near the face's own. The cell is set so
    that the two faces' capital H end on the same row.
    """
    if size._extra_at is None:
        cell_w = max(2, int(0.65 * size.em + 0.5))
        cell_h = 2 * cell_w
        ours = _mask_image(size, "H", 0, "L")
        theirs = _terminal_cell(0x48, cell_w, cell_h)
        a, b = _ink_bottom(ours), _ink_bottom(theirs)
        if a is None or b is None:
            a, b = size.baseline, int(0.75 * cell_h) - 1
        size._extra_at = (cell_w, cell_h, a - b)
    return size._extra_at


def _extra_cell(size, ch):
    cp = ord(ch)
    if cp in _NO_PICTURE:
        return (0, 0, 0, None, None)
    cell_w, cell_h, top = _extra_geometry(size)
    wide = unicodedata.east_asian_width(ch) in ("W", "F")
    advance = (2 * cell_w if wide else cell_w) + 1
    bold_advance = advance + size.stroke(1)
    cell = _terminal_cell(cp, cell_w, cell_h)
    if cell is None:
        return (advance, bold_advance, 0, None, None)
    grey = Image.new("L", (cell_w, size.rows), 0)
    grey.paste(cell, (0, top))
    bits = grey.point(lambda v: 255 if v >= 128 else 0).convert("1")
    if bits.getbbox() is None:
        return (advance, bold_advance, 0, None, None)
    return (advance, bold_advance, cell_w, bits, grey)


def _mixed_image(size, text, bold, mode):
    """A line with characters the face does not cover (ONLY). Caller holds
    size.lock."""
    width = size.mixed_width(text, bold)
    if width < 0:
        return None
    grey = size.scalable
    out = Image.new("L" if grey else "1", (width + size.em + 2, max(1, size.rows)), 0)
    pen = 0
    for covered, piece in size.runs(text):
        if covered:
            part = _mask_image(size, piece, bold, "L" if grey else "1")
            step = size.width(piece, bold)
            if part is None or step < 0:
                return None
            out.paste(255 if grey else 1, (pen, 0), part)
            pen += step
            continue
        adv, badv, w, bits, soft = size.extra(piece)
        if w:
            ink = soft if grey else bits
            for shift in range(size.stroke(bold) + 1):
                out.paste(255 if grey else 1, (pen + shift, 0), ink)
        pen += badv if bold else adv
    if grey or mode == "1":
        return out
    return out.convert("L")


def _mask(size, text, bold, mode):
    """Em-tall mask of the face. Rows are UI_TOP .. UI_TOP+em-1.

    Caller holds size.lock.
    """
    im = _mask_image(size, text, bold, mode)
    return None if im is None else im.im


def _mask_image(size, text, bold, mode):
    if size.scalable:
        mode = "L"
    if ONLY and not size.covers(text):
        return _mixed_image(size, text, bold, mode)
    data = text.encode("utf-8")
    width = size.width(text, bold)
    if width < 0:
        return None
    if (mode == "1" or size.slant) and width > 0 and size.letters is not None:
        im = size.letters.mask(text, bold, width)
        if im is not None:
            return im if mode == "1" else im.convert("L")
    if width == 0:
        return Image.new("1" if mode == "1" else "L", (1, max(1, size.rows)), 0)
    if size.slant:
        # Only the kept letters know the shear; a whole-line draw would be upright.
        return None
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
    elif _lib.has_bits:
        raw = ctypes.create_string_buffer(buf_w * buf_h)
        if _lib.neuronte_alpha_pack(buf, buf_w, buf_w, buf_h, raw, len(raw)) != 0:
            return None
        im = Image.frombytes("L", (buf_w, buf_h), raw.raw)
    else:
        raw = array.array("B", (px >> 24 for px in buf))
        im = Image.frombytes("L", (buf_w, buf_h), raw.tobytes())
    return im


_NONZERO = [0] + [255] * 255


def _pack_binary(buf, buf_w, buf_h):
    """Mode "1" image with a bit set wherever the 32-bit pixel is not zero.

    Pillow merges the four channels by maximum and cuts at one; a Python
    loop over the pixels took 25 times as long as the drawing itself.
    A library that has neuronte_bits_pack does it in one call.
    """
    if _lib is not None and _lib.has_bits:
        raw = ctypes.create_string_buffer(((buf_w + 7) // 8) * buf_h)
        if _lib.neuronte_bits_pack(buf, buf_w, buf_w, buf_h, raw, len(raw)) == 0:
            return Image.frombytes("1", (buf_w, buf_h), raw.raw)
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
_BITS_CELL = struct.Struct("=IHHHH")    # the library's neuronte_bits_cell
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
        if getattr(size, "slant", None):
            weights += _file_digest(_slant_path())
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
        # The same cells as the library lays them: one atlas of 1-bit rows,
        # a neuronte_bits_cell for each letter, and each letter's index.
        self._index = {}
        self._atlas = bytearray()
        self._records = bytearray()
        self._c = None        # ctypes copies of the two, made when a letter is added

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
        if ONLY and not size.covered(ch):
            # A terminal bundle's cell. It is kept by the size, not here: the
            # cells file is named by this face's weights alone.
            return size.extra(ch)[:4]
        data = ch.encode("utf-8")
        measure = size.slant or size.ptr
        adv = _lib.neuronte_text_width(measure, data, len(data), 0, size.em)
        badv = _lib.neuronte_text_width(measure, data, len(data), 1, size.em)
        if adv < 0 or badv < 0:
            return None
        buf_w, buf_h = adv + size.em + 2, size.rows
        buf = (ctypes.c_uint32 * (buf_w * buf_h))()
        if size.slant:
            # The upright letter's cell, an em wide and two high, sheared at the pen.
            rc = _lib.neuronte_draw_scalar_styled(
                size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
                0, -size.ui_top, size.em, 2 * size.em,
                _lib.neuronte_advance_scalar(size.slant, ord(ch)), 0xFFFFFFFF, 2)
        else:
            rc = _lib.neuronte_draw_text(
                size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
                0, -size.ui_top, size.em, 0, data, len(data), 0xFFFFFFFF)
        if rc < 0:
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

    def _add(self, ch):
        """Put this letter in the atlas. False when it cannot be drawn or
        does not fit a neuronte_bits_cell."""
        hit = self.cell(ch)
        if hit is None:
            return False
        adv, badv, width, im = hit
        if not (0 <= adv <= 0xFFFF and 0 <= badv <= 0xFFFF and 0 <= width <= 0xFFFF):
            return False
        self._records += _BITS_CELL.pack(len(self._atlas), width, adv, badv, 0)
        if width:
            self._atlas += im.tobytes()
        self._index[ch] = len(self._index)
        self._c = None
        return True

    def _compose(self, text, bold, width):
        """The string laid by the library from the kept letters, or None."""
        index = self._index
        try:
            order = [index[ch] for ch in text]
        except KeyError:
            for ch in text:
                if ch not in index and not self._add(ch):
                    return None
            order = [index[ch] for ch in text]
        if self._c is None:
            self._c = (ctypes.create_string_buffer(bytes(self._records), len(self._records)),
                       ctypes.create_string_buffer(bytes(self._atlas), max(1, len(self._atlas))))
        records, atlas = self._c
        size = self.size
        out_w = width + size.em + 2
        out = ctypes.create_string_buffer(((out_w + 7) // 8) * size.rows)
        pen = _lib.neuronte_bits_compose(
            out, len(out), out_w, size.rows, atlas, len(self._atlas),
            records, len(index), (ctypes.c_uint32 * len(order))(*order), len(order),
            1 if bold else 0)
        if pen != width:
            return None
        return Image.frombytes("1", (out_w, size.rows), out.raw)

    def mask(self, text, bold, width):
        """The string's mask, or None so the caller asks the library."""
        size = self.size
        if _lib.has_bits:
            return self._compose(text, bold, width)
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
        if ONLY:
            # There is no other face: an uncovered character is a terminal
            # bundle's cell or the untrained mark, and a layout request is
            # laid left to right like any other.
            return True
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

    def _offset(self, anchor, text=None):
        if anchor in (None, "la", "lt"):
            return (0, 0)
        if anchor == "ls":
            return (0, -self._face.baseline)
        if not ONLY or len(anchor) != 2:
            return None
        # Every anchor, since no other face can take the request. Caller
        # holds the face lock.
        width = max(0, self._face.width(text, self.bold)) if text else 0
        rows = self._face.rows
        x = {"l": 0, "m": -(width // 2), "r": -width}.get(anchor[0], 0)
        y = {"a": 0, "t": 0, "m": -(rows // 2), "s": -self._face.baseline,
             "b": -rows, "d": -rows}.get(anchor[1], 0)
        return (x, y)

    def getlength(self, text, mode="", direction=None, features=None,
                  language=None):
        s = _as_text(text)
        with self._face.lock:
            if not self._use_face(s, direction, features, language):
                return self._fallback_font.getlength(
                    s, mode, direction, features, language)
            return max(0, self._face.width(s, self.bold)) if ONLY else self._face.width(s, self.bold)

    def getbbox(self, text, mode="", direction=None, features=None,
                language=None, stroke_width=0, anchor=None):
        s = _as_text(text)
        with self._face.lock:
            off = self._offset(anchor, s)
            if off is None or not self._use_face(s, direction, features, language, stroke_width):
                return self._fallback_font.getbbox(
                    s, mode, direction, features, language, stroke_width, anchor)
            width = self._face.width(s, self.bold)
        left, top = off
        stroke = int(stroke_width or 0)
        return (left, top - stroke, left + max(0, width) + 2 * stroke,
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
        with self._face.lock:
            off = self._offset(anchor, s)
            if off is None or not self._use_face(s, direction, features, language, stroke_width):
                return self._fallback_font.getmask2(
                    s, mode, direction, features, language, stroke_width,
                    anchor, ink, start, *args, **kwargs)
            mask = _mask(self._face, s, self.bold, mode)
            if mask is None:
                if ONLY:
                    # Nothing else may draw it: an empty line of the right height.
                    blank = Image.new("L" if self._face.scalable or mode != "1" else "1",
                                      (1, max(1, self._face.rows)), 0)
                    return blank.im, off
                return self._fallback_font.getmask2(
                    s, mode, direction, features, language, stroke_width,
                    anchor, ink, start, *args, **kwargs)
        return mask, off

    def font_variant(self, font=None, size=None, index=None, encoding=None,
                     layout_engine=None):
        if font is not None and not ONLY:
            return self._fallback_font.font_variant(
                font=font, size=size, index=index, encoding=encoding,
                layout_engine=layout_engine)
        new = self.size if size is None else int(round(float(size)))
        return self._variant(new, bold=bool(self.bold), italic=self.italic)


def _only_open(em, italic):
    if kind(em, italic) is None:
        return None
    face = open_size(em, italic)
    if face is None or (face.scalable and not _lib.has_stroke):
        return None
    return face


def only_face(size, italic=False):
    """ONLY: the face that draws this size and slant. An italic with no file
    is the upright face of that size; a size with no file is the nearest
    that has one. (face, True when it is the asked slant), or (None, False)."""
    size = int(size)
    if italic:
        face = _only_open(size, True)
        if face is not None:
            return face, True
    for em in sorted(range(1, 257), key=lambda em: (abs(em - size), em)):
        face = _only_open(em, False)
        if face is not None:
            return face, not italic
    return None, False


def only_font(size, bold, variant, italic=False):
    """ONLY: a NeuronteFont for any size and style, with no other face
    behind it. Raises when this tree cannot draw at all."""
    face, _exact = only_face(size, italic)
    if face is None or not _library().has_untrained:
        raise RuntimeError(
            "KILIX_NEURONTE_ONLY=1, but no Neuronte face can be opened from %r "
            "(it needs build/libneuronte.so of Neuronte 2.2 or later and weights/)" % _ROOT)
    return NeuronteFont(size, bold, _face_file(face, italic), face, None, variant, italic)


def _face_file(face, italic):
    path = weight_path(face.em, italic)
    return path if os.path.isfile(path) else weight_path(face.em, False)


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
