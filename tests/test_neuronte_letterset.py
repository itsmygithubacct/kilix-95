"""The letter cells kept on disk give what the net draws, or are not used.

A small face saves its cells in the Kilix 95 cache and reads them at the
next start. Here a face is drawn, saved and read again in throwaway caches:
the read cells make the same pixels as the library's own drawing of each
string, without one call into the net. A file that is damaged, linked,
foreign, too large or out of range reads as nothing, and the face draws and
saves again. A cache that cannot be written changes no pixel.
"""
import atexit
import ctypes
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import types

# Every cache this test touches is its own, from the first import on.
ROOT = tempfile.mkdtemp(prefix="kilix95-letterset-")
atexit.register(shutil.rmtree, ROOT, True)
os.environ["KILIX95_CACHE_HOME"] = os.path.join(ROOT, "import")
# The file's mode is the writer's own choice, whatever the caller's umask.
os.umask(0)

import harness as H  # noqa: E402,F401  (isolated storage before the desktop imports)
import neuronte_face as N  # noqa: E402
import theme as T  # noqa: E402
from neuronte_face_check import ITALIC, UPRIGHT, require  # noqa: E402

require(all(N.open_size(em) for em in (10, 11)), "no Neuronte 10px or 11px weights")

# The desktop's own start-up thread draws too: let it end before counting.
for running in threading.enumerate():
    if running.name == "neuronte-letters":
        running.join(60)
        assert not running.is_alive()

# Calls into the net: every drawing goes through this entry point.
DRAW = N._lib.neuronte_draw_text
calls = [0]


def counted(*args):
    calls[0] += 1
    return DRAW(*args)


N._lib.neuronte_draw_text = counted


def use_cache(name):
    """Point the Kilix 95 cache at ROOT/name; the folder the cells go in."""
    base = os.path.join(ROOT, name)
    os.environ["KILIX95_CACHE_HOME"] = base
    return os.path.join(base, "neuronte")


def reopen(em, italic=False):
    """The face as a new process would open it."""
    N._sizes.pop((em, italic), None)
    size = N.open_size(em, italic)
    assert size is not None, (em, italic)
    return size


def warm(size):
    """What theme.py does at start; True when a thread had to draw."""
    thread = N.start_letters((types.SimpleNamespace(_face=size),))
    if thread is None:
        return False
    thread.join(60)
    assert not thread.is_alive()
    return True


def library_mask(size, text, bold):
    """The string drawn by the library in one call, packed by a pixel loop."""
    data = text.encode("utf-8")
    width = size.width(text, bold)
    buf_w, buf_h = width + size.em + 2, size.rows
    buf = (ctypes.c_uint32 * (buf_w * buf_h))()
    assert DRAW(
        size.ptr, ctypes.cast(buf, ctypes.c_void_p), buf_w, buf_w, buf_h,
        0, -size.ui_top, size.em, int(bool(bold)), data, len(data), 0xFFFFFFFF) >= 0
    row_b = (buf_w + 7) // 8
    packed = bytearray(row_b * buf_h)
    for i, px in enumerate(buf):
        if px:
            y, x = divmod(i, buf_w)
            packed[y * row_b + (x >> 3)] |= 0x80 >> (x & 7)
    return (buf_w, buf_h), bytes(packed)


def cell_mask(size, text, bold):
    with size.lock:
        out = size.letters.mask(text, bold, size.width(text, bold))
    assert out is not None, (size.em, bold, text)
    return out.size, out.tobytes()


def plain(cells):
    return {cp: (adv, badv, width, im.tobytes() if im else b"")
            for cp, (adv, badv, width, im) in cells.items()}


def build(cells, magic=b"NRTATLAS", tail=b""):
    """A cells file written from the format's description, not by the face."""
    body = b""
    for cp, (adv, badv, width, bits) in sorted(cells.items()):
        body += struct.pack("<IHHH", cp, adv, badv, width) + bits
    body += tail
    return magic + body + hashlib.sha256(body).digest()


def listing(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else None


rng = random.Random(1995)
letters = [chr(c) for c in range(32, 127)] + ["…"]
corpus = ["Start", "My Computer", "12:08 AM", "WAVE AWAY fjord_Typ.{}[]|\\~^`$",
          "…", "a", "ff ij ll WW //", "budget 2026.txt", "".join(letters)]
corpus += ["".join(rng.choice(letters) for _ in range(rng.randint(1, 30)))
           for _ in range(30)]
COMMON = {ord(ch) for ch in N.COMMON}

faces = [(10, False), (11, False)]
slanted = [em for em in ITALIC if em <= 32]
if slanted:
    faces.append((11 if 11 in slanted else slanted[0], True))
good = {}        # face -> (file path, file bytes, library masks)
# One cache for every face, as on a desktop: each finds its own file.
folder = use_cache("trip")
files = []

for em, italic in faces:
    size = reopen(em, italic)
    assert size.letters.path and os.path.dirname(size.letters.path) == folder
    assert listing(folder) == sorted(files) and size.letters.cells == {}
    with size.lock:
        want = {(text, bold): library_mask(size, text, bold)
                for text in corpus for bold in (0, 1)}

    # First run: the thread draws the set through the net and saves it.
    calls[0] = 0
    assert warm(size)
    assert calls[0] == len(N.COMMON), calls[0]
    assert set(size.letters.cells) == COMMON
    path = size.letters.path
    # One file for the face, regular and bold; no temporary file is left.
    files.append(os.path.basename(path))
    assert len(set(files)) == len(files) and listing(folder) == sorted(files), listing(folder)
    info = os.lstat(path)
    assert info.st_mode & 0o7777 == 0o600 and info.st_uid == os.geteuid()
    data = open(path, "rb").read()
    drawn = plain(size.letters.cells)
    # The file is the documented format and nothing else.
    assert data == build(drawn)
    assert len(drawn) == 96
    for key, value in want.items():
        assert cell_mask(size, *key) == value, (em, italic, key)

    # Next start: the cells come from the file. Nothing is drawn through
    # the net, no thread starts, and every string is the library's drawing.
    calls[0] = 0
    size = reopen(em, italic)
    assert size.letters.path == path
    assert plain(size.letters.cells) == drawn
    assert not warm(size)
    for key, value in want.items():
        assert cell_mask(size, *key) == value, (em, italic, key)
        with size.lock:
            core = N._mask(size, key[0], key[1], "1")
        im = N.Image.new("1", core.size)
        im.im = core
        assert (im.size, im.tobytes()) == value, (em, italic, key)
    assert calls[0] == 0, calls[0]
    # Nothing new to save: the file is not written again.
    os.chmod(path, 0o400)
    N.save_letters()
    assert os.lstat(path).st_mode & 0o7777 == 0o400
    os.chmod(path, 0o600)
    assert open(path, "rb").read() == data and listing(folder) == sorted(files)
    good[em, italic] = (path, data, want)

# Each face has its own file, and reads its own cells from the shared cache.
assert len(files) == len(faces)
for em, italic in faces:
    size = reopen(em, italic)
    assert N._pack_cells(size.letters.cells) == good[em, italic][1]


# A file that is wrong in any way reads as nothing.
em, italic = faces[0]
path, data, want = good[em, italic]
size = reopen(em, italic)
rows = size.rows
drawn = plain(size.letters.cells)
scratch = os.path.join(ROOT, "scratch.bin")


def reads(blob, at=scratch):
    with open(at, "wb") as fh:
        fh.write(blob)
    got = N._read_cells(at, em, rows)
    return None if got is None else plain(got)


assert reads(data) == drawn
for at in range(len(data)):                      # any one flipped byte
    assert reads(data[:at] + bytes([data[at] ^ 0x20]) + data[at + 1:]) is None, at
for cut in range(len(data)):                     # any truncation, and empty
    assert not reads(data[:cut]), cut
assert reads(b"") is None
assert reads(build(drawn, magic=b"NRTATLAZ")) is None        # digest still right
assert reads(build(drawn, magic=b"")) is None
assert N._read_cells(os.path.join(ROOT, "absent.bin"), em, rows) is None
assert N._read_cells("", em, rows) is None

# Fields out of range, each in a file whose digest is right.
some = min(cp for cp, cell in drawn.items() if cell[2])
adv, badv, width, bits = drawn[some]
row_bytes = (width + 7) // 8


def with_cell(cp, cell):
    out = dict(drawn)
    out.pop(some)
    out[cp] = cell
    return out


assert reads(build(with_cell(some, drawn[some]))) == drawn
assert reads(build(with_cell(0x10FFFF, drawn[some]))) is not None
assert reads(build(with_cell(0x110000, drawn[some]))) is None
assert reads(build(with_cell(some, (4096, badv, width, bits)))) is not None
assert reads(build(with_cell(some, (4097, badv, width, bits)))) is None
assert reads(build(with_cell(some, (adv, 4096, width, bits)))) is not None
assert reads(build(with_cell(some, (adv, 4097, width, bits)))) is None
wide = adv + em + 2
assert reads(build(with_cell(some, (adv, badv, wide, bytes((wide + 7) // 8 * rows))))) is not None
wide += 1
assert reads(build(with_cell(some, (adv, badv, wide, bytes((wide + 7) // 8 * rows))))) is None
# A width that claims more pixel bytes than the file holds, in the last cell.
last = max(drawn)
short = dict(drawn)
short[last] = (40, 41, 40, bytes(5 * rows - 1))
assert reads(build(short)) is None
short[last] = (40, 41, 40, bytes(5 * rows))
assert reads(build(short)) is not None
# Bytes after the last cell that are not a cell.
assert reads(build(drawn, tail=b"\0" * 9)) is None
# The same scalar twice.
assert reads(build(drawn, tail=struct.pack("<IHHH", some, adv, badv, 0))) is None
assert reads(build(drawn, tail=struct.pack("<IHHH", 0x2603, adv, badv, 0))) is not None

# Oversize: right in every other way, one byte past the limit and at it.
room = N._CELLS_LIMIT - len(data)
assert room > 0 and N._CELLS_LIMIT <= 1 << 20
fill = b"".join(struct.pack("<IHHH", 0x20000 + i, 1, 2, 0) for i in range(room // 10 + 1))
at_limit = build(drawn, tail=fill[:room // 10 * 10])
assert len(at_limit) <= N._CELLS_LIMIT and reads(at_limit) is not None
over = build(drawn, tail=fill)
assert len(over) > N._CELLS_LIMIT and reads(over) is None
with open(scratch, "wb") as fh:                              # a sparse giant
    fh.write(data)
    fh.truncate(1 << 31)
assert N._read_cells(scratch, em, rows) is None

# A link is not followed, even to a good file; nor a pipe waited for.
assert reads(data) == drawn
link = os.path.join(ROOT, "link.bin")
os.symlink(scratch, link)
assert N._read_cells(link, em, rows) is None
os.unlink(link)
pipe = os.path.join(ROOT, "pipe.bin")
os.mkfifo(pipe)
assert N._read_cells(pipe, em, rows) is None
os.unlink(pipe)
os.mkdir(pipe)
assert N._read_cells(pipe, em, rows) is None
os.rmdir(pipe)

# A file some other user owns.
mine = os.geteuid
os.geteuid = lambda: mine() + 1
try:
    assert N._read_cells(scratch, em, rows) is None
finally:
    os.geteuid = mine
assert N._read_cells(scratch, em, rows) is not None


# The whole way round for damaged files: the face opens with no cells,
# draws through the net on the thread, shows the same pixels and puts the
# good file back.
def falls_back(label):
    calls[0] = 0
    size = reopen(em, italic)
    assert size.letters.path == path
    assert size.letters.cells == {}, label
    assert warm(size), label
    assert calls[0] == len(N.COMMON), (label, calls[0])
    for key, value in want.items():
        assert cell_mask(size, *key) == value, (label, key)
    assert not os.path.islink(path) and open(path, "rb").read() == data, label
    assert listing(folder) == sorted(files), label


middle = len(data) // 2
damaged = {
    "flipped byte": data[:middle] + bytes([data[middle] ^ 1]) + data[middle + 1:],
    "truncated": data[:middle],
    "wrong magic": build(drawn, magic=b"NRTATLAZ"),
    "empty": b"",
    "out of range": build(with_cell(0x110000, drawn[some])),
    "oversize": over,
}
for label, blob in damaged.items():
    with open(path, "wb") as fh:
        fh.write(blob)
    falls_back(label)

# A link where the file should be, to a good copy outside the cache.
outside = os.path.join(ROOT, "outside.bin")
with open(outside, "wb") as fh:
    fh.write(data)
os.unlink(path)
os.symlink(outside, path)
falls_back("symlink")
assert open(outside, "rb").read() == data


# A short write must finish before replacing the old file. An error after
# a partial write, or a write that makes no progress, keeps the old file.
write_path = os.path.join(ROOT, "short-write.bin")
write = os.write
try:
    os.write = lambda fd, chunk: write(fd, chunk[:7])
    assert N._write_private(write_path, data)
    assert open(write_path, "rb").read() == data

    writes = [0]

    def full_disk(fd, chunk):
        writes[0] += 1
        if writes[0] > 1:
            raise OSError("disk full")
        return write(fd, chunk[:7])

    os.write = full_disk
    assert not N._write_private(write_path, data + b"changed")
    assert open(write_path, "rb").read() == data
    os.write = lambda fd, chunk: 0
    assert not N._write_private(write_path, data + b"changed")
    assert open(write_path, "rb").read() == data
    assert not os.path.exists("%s.%d.tmp" % (write_path, os.getpid()))
finally:
    os.write = write


# Read-only cache. The cache folder cannot be made: no path, nothing
# written, the same pixels from memory.
locked = os.path.join(ROOT, "locked")
os.mkdir(locked)
os.chmod(locked, 0o500)
unwritable = os.geteuid() != 0
try:
    if unwritable:
        use_cache(os.path.join("locked", "cache"))
        calls[0] = 0
        size = reopen(em, italic)
        assert size.letters.path == "" and size.letters.cells == {}
        assert warm(size) and calls[0] == len(N.COMMON)
        N.save_letters()
        for key, value in want.items():
            assert cell_mask(size, *key) == value, key
        assert os.listdir(locked) == []
finally:
    os.chmod(locked, 0o700)

# The folder is there but takes no file: the write fails and is ignored.
frozen = use_cache("frozen")
size = reopen(em, italic)
assert size.letters.path and listing(frozen) == []
os.chmod(frozen, 0o500)
try:
    if unwritable:
        assert warm(size)
        assert size.letters.unsaved
        N.save_letters()
        for key, value in want.items():
            assert cell_mask(size, *key) == value, key
        assert listing(frozen) == []
finally:
    os.chmod(frozen, 0o700)
# Once it can be written, the end-of-run save writes the same file.
if unwritable:
    N.save_letters()
    assert open(size.letters.path, "rb").read() == data
    assert listing(frozen) == [os.path.basename(path)]
    assert not size.letters.unsaved


# A size opened after start has no thread: its cells are saved at the end
# of the run, read at the next, and completed by whoever draws the rest.
em2, italic2 = faces[1]
late = use_cache("late")
size = reopen(em2, italic2)
used = "Start"
for bold in (0, 1):
    assert cell_mask(size, used, bold) == good[em2, italic2][2][used, bold]
assert listing(late) == []
N.save_letters()
assert listing(late) == [os.path.basename(size.letters.path)]
calls[0] = 0
size = reopen(em2, italic2)
assert set(size.letters.cells) == {ord(ch) for ch in used}
for bold in (0, 1):
    assert cell_mask(size, used, bold) == good[em2, italic2][2][used, bold]
assert calls[0] == 0
assert warm(size)
assert calls[0] == len(N.COMMON) - len(set(used))
assert open(size.letters.path, "rb").read() == good[em2, italic2][1]


# The file name follows the bytes of the weight file and of the library,
# and what the cells were drawn with.
use_cache("names")
size = N.open_size(em, italic)
real_weight, real_name = N.weight_path, N._lib._name
base = N._cells_path(size, italic)
assert base and os.path.basename(base) == os.path.basename(path)
assert N._cells_path(size, italic) == base


def copy_of(source, name, flip=None):
    blob = bytearray(open(source, "rb").read())
    if flip is not None:
        blob[flip] ^= 1
    target = os.path.join(ROOT, name)
    with open(target, "wb") as fh:
        fh.write(blob)
    return target


weights = real_weight(em, italic)
library = real_name
try:
    names = {base}
    # The same bytes somewhere else are the same file name.
    N.weight_path = lambda *a: copy_of(weights, "same.nrt")
    assert N._cells_path(size, italic) == base
    N.weight_path = lambda *a: copy_of(weights, "other.nrt", flip=-1)
    names.add(N._cells_path(size, italic))
    N.weight_path = lambda *a: os.path.join(ROOT, "no-such.nrt")
    assert N._cells_path(size, italic) == ""
    N.weight_path = real_weight
    N._lib._name = copy_of(library, "same.so")
    assert N._cells_path(size, italic) == base
    N._lib._name = copy_of(library, "other.so", flip=-1)
    names.add(N._cells_path(size, italic))
    N._lib._name = os.path.join(ROOT, "no-such.so")
    assert N._cells_path(size, italic) == ""
    N._lib._name = real_name
    N.weight_path = lambda *a: weights
    names.add(N._cells_path(size, not italic))
    for field, value in (("em", size.em + 1), ("rows", size.rows + 1),
                         ("ui_top", size.ui_top + 1)):
        shifted = types.SimpleNamespace(em=size.em, rows=size.rows, ui_top=size.ui_top)
        setattr(shifted, field, value)
        names.add(N._cells_path(shifted, italic))
    N.weight_path = real_weight
    saved = N._CELLS_FORMAT
    N._CELLS_FORMAT = saved + 1
    names.add(N._cells_path(size, italic))
    N._CELLS_FORMAT = saved
    assert "" not in names and len(names) == 8, names
finally:
    N.weight_path, N._lib._name = real_weight, real_name

# The desktop itself: a run that opens another size saves it when it ends,
# with no call from here.
others = [n for n in UPRIGHT if n not in (T.FONT.size, T.SMALL.size)]
if others:
    at_exit = use_cache("exit")
    other = others[0]
    script = ("import harness, theme as T, neuronte_face as N\n"
              "font = T.font_at(%d)\n"
              "assert isinstance(font, N.NeuronteFont)\n"
              "font.getmask('Start', '1')\n"
              "print(font._face.letters.path)\n" % other)
    run = subprocess.run([sys.executable, "-c", script], capture_output=True,
                         text=True, timeout=60, cwd=os.path.dirname(os.path.abspath(__file__)))
    assert run.returncode == 0, run.stderr
    written = run.stdout.strip()
    assert os.path.dirname(written) == at_exit, written
    kept = N._read_cells(written, other, other)
    assert kept is not None and set(kept) == {ord(ch) for ch in "Start"}
print("ok")
