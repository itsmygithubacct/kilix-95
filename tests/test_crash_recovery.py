"""Crash recovery: zero-width selection draws, per-window fault isolation,
unsaved-document checkpoints and their restore after a provider restart."""
import harness as H
from apps.wordpad import WordPad


def _wordpad(desk, text):
    w = WordPad(desk)
    desk.wm.add(w)
    w.rta.set_plain(text)
    w.modified = False
    return w


# ── D1: select-all over a trailing empty paragraph must render ──────────────
# A file ending in a newline loads as ["line", ""]; select-all then ends at
# (1, 0), whose empty last line has a zero-width selection segment. That
# segment used to reach Pillow as x1 = x0 - 1 and killed the provider.
d = H.make_desk()
w = _wordpad(d, "WordPad saved line\n")
assert len(w.rta.paras) == 2, w.rta.paras
d.wm.activate(w)
w.set_focus(w.rta)
H.key(d, "a", ctrl=True)
assert w.rta._sel() is not None, "select-all selected nothing"
w.invalidate()
w.render()                                # must not raise

# a selection that starts and ends on the same empty paragraph
w2 = _wordpad(d, "first\n\nthird")
w2.rta.anchor = (0, 2)
w2.rta.caret = (2, 3)                     # spans the empty middle paragraph
w2.invalidate()
w2.render()

# ── D1b: deleting a multi-paragraph selection re-lays out before drawing ────
# Backspace/Delete edited the paragraphs without bumping the layout version,
# so the next draw walked cached lines for paragraphs that no longer existed
# (IndexError) and a delete-only edit never marked the document modified.
w3 = _wordpad(d, "WordPad saved line\nsecond\nthird")
d.wm.activate(w3)
w3.set_focus(w3.rta)
w3.render()                               # lay out three paragraphs
H.key(d, "a", ctrl=True)
H.key(d, "Backspace", text="")
assert len(w3.rta.paras) == 1, w3.rta.paras
w3.invalidate()
w3.render()                               # must not raise
assert w3.modified, "deleting text must mark the document modified"

w4 = _wordpad(d, "one\ntwo")
d.wm.activate(w4)
w4.set_focus(w4.rta)
w4.render()
w4.rta.caret, w4.rta.anchor = (0, 3), None
H.key(d, "Delete", text="")               # joins the paragraphs
assert len(w4.rta.paras) == 1
w4.invalidate()
w4.render()
assert w4.modified, "Delete must mark the document modified"

# ── D1: a focused text field whose selection lies past its visible width ────
import widgets as W                       # noqa: E402
import wm                                 # noqa: E402

holder = wm.Window(d, "field", 200, 80)
d.wm.add(holder)
field = holder.add(W.TextField(4, 4, 60, "x" * 200))
holder.set_focus(field)
field.scroll = 0                          # viewport shows the start of the text
field.anchor, field.cur = 150, 180        # selection entirely beyond the viewport
holder.invalidate()
holder.render()                           # must not raise
d.wm.close(holder)


# ── helpers ─────────────────────────────────────────────────────────────────
import os                                 # noqa: E402
import tempfile                           # noqa: E402

import doc_recovery                       # noqa: E402
from apps.notepad import Notepad          # noqa: E402


def box(desk, title):
    for win in reversed(desk.wm.windows):
        if win.title == title:
            return win
    return None


def press(win, label):
    for wdg in win.widgets:
        if isinstance(wdg, W.Button) and wdg.text == label:
            wdg.cb()
            return
    raise AssertionError(f"no {label!r} button in {win.title!r}")


def notepad(desk, path, text):
    with open(path, "w") as fh:
        fh.write("saved\n")
    np = Notepad(desk, path)
    desk.wm.add(np)
    desk.wm.activate(np)
    np.ta.set_text(text)
    np._changed()
    return np


clock = [1000.0]


def tick(desk):
    clock[0] += doc_recovery.INTERVAL + 0.01
    doc_recovery.tick(desk, clock[0])


tmp = tempfile.mkdtemp(prefix="crash-recovery-")

# ── D2: a window that fails to draw is closed; the desktop and others live ──
d = H.make_desk()
survivor = notepad(d, os.path.join(tmp, "survivor.txt"), "keep me")


class Broken(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, "Broken App", 200, 120)
        self.fail_draw = self.fail_key = self.fail_mouse = False

    def render(self):
        if self.fail_draw:
            raise ValueError("draw fault")
        return super().render()

    def on_key(self, ev):
        if self.fail_key:
            raise RuntimeError("key fault")
        return super().on_key(ev)

    def on_mouse(self, ev):
        if self.fail_mouse:
            raise RuntimeError("mouse fault")
        return super().on_mouse(ev)


import contextlib                         # noqa: E402
import io                                 # noqa: E402
import storage                            # noqa: E402

bad = Broken(d)
d.wm.add(bad)
bad.fail_draw = True
d.dirty = True
captured = io.StringIO()
with contextlib.redirect_stderr(captured):
    d.render()                            # must not raise
assert captured.getvalue() == "", "a fault report must not be painted over the desktop"
with open(storage.state_dir("crash.log")) as fh:
    log = fh.read()
assert "Broken failed during drawing" in log and "ValueError: draw fault" in log, log
assert oct(os.stat(storage.state_dir("crash.log")).st_mode & 0o777) == "0o600"
assert bad not in d.wm.windows
assert survivor in d.wm.windows
err = box(d, "Program Error")
assert err is not None, [w.title for w in d.wm.windows]
press(err, "OK")

bad = Broken(d)
d.wm.add(bad)
d.wm.activate(bad)
bad.fail_key = True
H.key(d, "x")                             # must not raise
assert bad not in d.wm.windows
press(box(d, "Program Error"), "OK")

bad = Broken(d)
d.wm.add(bad)
bad.x, bad.y = 300, 300
bad.fail_mouse = True
H.click(d, 320, 340)                      # must not raise
assert bad not in d.wm.windows
press(box(d, "Program Error"), "OK")

# the loop-level net absorbs isolated faults but gives up on a fault storm
d._loop_faults = []
for _ in range(5):
    try:
        raise RuntimeError("isolated")
    except RuntimeError:
        d._loop_fault()
try:
    try:
        raise RuntimeError("storm")
    except RuntimeError:
        d._loop_fault()
except RuntimeError:
    pass
else:
    raise AssertionError("six faults in ten seconds must end the desktop")

# ── D3: unsaved text is checkpointed, then dropped once saved ───────────────
for token, _record in doc_recovery.pending():
    doc_recovery._forget(token)
p1 = os.path.join(tmp, "one.txt")
np = notepad(d, p1, "line one\nUNSAVED-ONE")
tick(d)
[(token, record)] = doc_recovery.pending()
assert record["app"] == "notepad" and record["path"] == p1, record
assert record["snapshot"]["text"] == "line one\nUNSAVED-ONE"
np.ta.set_text("line one\nUNSAVED-ONE-more")
tick(d)
[(_t, record)] = doc_recovery.pending()
assert record["snapshot"]["text"].endswith("-more"), "edits are re-checkpointed"
np._save()
tick(d)
assert doc_recovery.pending() == [], "a saved document keeps no checkpoint"

# deliberate close without saving drops it too
np2 = notepad(d, os.path.join(tmp, "two.txt"), "discard me")
tick(d)
assert len(doc_recovery.pending()) == 1
np2.request_close()
press(box(d, "Notepad"), "No")
assert doc_recovery.pending() == [], "a discarded document keeps no checkpoint"
survivor._save()
tick(d)

# ── D2+D3: a failing editor keeps its text and can reopen it ────────────────
p3 = os.path.join(tmp, "three.txt")
np3 = notepad(d, p3, "line\nUNSAVED-THREE")
tick(d)


def boom():
    raise ValueError("draw fault")


np3.render = boom
d.dirty = True
d.render()
assert np3 not in d.wm.windows
[(old_token, _r)] = doc_recovery.pending()
err = box(d, "Program Error")
press(err, "Reopen")
again = H.find_window(d, "Notepad")
assert again is not None and again is not np3
assert again.ta.text() == "line\nUNSAVED-THREE" and again.modified and again.path == p3
[(new_token, record)] = doc_recovery.pending()
assert new_token != old_token, "the reopened window owns a fresh record"
assert record["snapshot"]["text"] == "line\nUNSAVED-THREE"
with open(p3) as fh:
    assert fh.read() == "saved\n", "restore never writes the user's file"

# ── D3: a desktop that dies offers the documents on its next start ──────────
wp = _wordpad(d, "rich base")
d.wm.activate(wp)
wp.path = os.path.join(tmp, "four.krt")
wp.rta.anchor, wp.rta.caret = (0, 0), (0, 4)
wp.rta.toggle("bold")
wp._changed()
tick(d)
assert len(doc_recovery.pending()) == 2
rich = wp.rta.to_obj()

d2 = H.make_desk()                        # same state home: a restarted desktop
d2._start_document_recovery()
offer = box(d2, "Document Recovery")
assert offer is not None
press(offer, "Restore")
pads = [w for w in d2.wm.windows if type(w).__name__ == "Notepad"]
pads_text = [w.ta.text() for w in pads]
assert "line\nUNSAVED-THREE" in pads_text, pads_text
wps = [w for w in d2.wm.windows if type(w).__name__ == "WordPad"]
assert len(wps) == 1 and wps[0].rta.to_obj() == rich, "rich text restored exactly"
assert all(w.modified for w in pads + wps)
assert len(doc_recovery.pending()) == 2, "restored documents stay protected"

# "Later" keeps them; a second offer shows the same two, no duplicates
d3 = H.make_desk()
d3._start_document_recovery()
press(box(d3, "Document Recovery"), "Later")
assert len(doc_recovery.pending()) == 2
d4 = H.make_desk()
d4._start_document_recovery()
press(box(d4, "Document Recovery"), "Discard")
assert doc_recovery.pending() == []

# ── D3: an oversized document is named as lost, never silently dropped ─────
big = notepad(d, os.path.join(tmp, "big.txt"), "x")
saved_max = doc_recovery.MAX_DOCUMENT
doc_recovery.MAX_DOCUMENT = 16
big.ta.set_text("y" * 64)
tick(d)
doc_recovery.MAX_DOCUMENT = saved_max
[(_t, record)] = doc_recovery.pending()
assert record.get("too_large") and "snapshot" not in record
d5 = H.make_desk()
d5._start_document_recovery()
lost = box(d5, "Document Recovery")
assert lost is not None
press(lost, "OK")
assert doc_recovery.pending() == []

assert doc_recovery.app_label("wordpad") == "WordPad"
assert doc_recovery.app_label("notepad") == "Notepad"

print("ok")
