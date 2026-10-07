"""Regressions from the B1 independent review (fix round 1).

1. Laying out the largest bounded output must not stall the UI thread.
2. The End confirmation and every message box expose their text to the
   accessibility tree.
3. A read-only text view refuses every edit, including through accessibility
   and paste, while navigation, selection and copy still work.
(The confirmation's complete-ID/command display and the receipt fixtures are
checked in test_ptysessions.py and test_ptysessions_contract.py.)
"""
import os
import time

import harness as H
import pty_fake as F
import theme as T
import widgets as W
import wm
from accessibility import Tree
from apps import ptysessions as P
from apps.notepad import Notepad

os.environ.pop("KITTY_PTY_BROKER_SESSION", None)
fake = F.FakeKilix(F.standard_responses())
P.kilix_launcher = lambda: fake.path
d = H.make_desk()


def best_of(n, fn):
    best = 1e9
    for _ in range(n):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


# ── 1. bounded layout cost ──────────────────────────────────────────────────
# The review measured 12 s for one 65,536-character line; layout is now
# linear (a few tens of ms). The bound is loose so a loaded host cannot trip
# it, and still two orders of magnitude below the old behaviour.
BOUND = 0.6
cases = {"one ascii line": "x" * 65536,
         "one multibyte line": "界" * 65536,
         "mixed prose": "ab 界 W " * 9000,
         "200 long lines": "\n".join("x" * 326 for _ in range(200))}
for name, text in cases.items():
    data = P._bounded_text({"text": text, "truncated": False}, "test")
    box = []
    opened = best_of(3, lambda: box.append(
        P.OutputWindow(d, "t", "banner", data["text"])))
    win = box[-1]
    assert opened < BOUND, (name, "open", opened)
    assert "".join(win.view.lines) == data["text"].replace("\n", ""), name
    limit = win.view.w - T.SCROLL_W - 10
    assert all(T.text_w(win.view.font, line) <= limit + 1
               for line in win.view.lines[:300]), name

    def resize():
        win.w += 23 if win.w < 900 else -300
        win.on_resize()
    resized = best_of(3, resize)
    assert resized < BOUND, (name, "resize", resized)
    assert "".join(win.view.lines) == data["text"].replace("\n", ""), name
    d.dirty = True
    d.render()
    win.close()

# through the real job path: the UI-thread part of a finished preview
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text="x" * 65536, total_bytes=65536))] + F.standard_responses())
win = P.PtySessions(d)
d.wm.add(win)
end = time.time() + 8
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
win.list.sel = 1
win._select_session(win.list.items[1])
win._preview()
future = win.futures["preview"][0]
future.result(timeout=10)
spent = best_of(1, lambda: win._tick(time.time()))
assert spent < BOUND, spent
view = H.find_window(d, "OutputWindow")
assert view is not None and "".join(view.view.lines) == "x" * 65536
view.close()
win.close()

# ── wrap_lines: nothing lost, rows fit, words mode keeps words ──────────────
rows = P.wrap_lines("W" * 64, 120)
assert "".join(rows) == "W" * 64 and len(rows) > 1
assert all(T.text_w(T.FONT, r) <= 121 for r in rows)
assert P.wrap_lines("", 100) == [""]
assert P.wrap_lines("a\n\nb", 100) == ["a", "", "b"]
prose = P.wrap_lines("one two three four five six seven", 80, words=True)
assert " ".join(prose).split() == "one two three four five six seven".split()
assert all(T.text_w(T.FONT, r) <= 81 for r in prose), prose
assert len(P.wrap_lines("x" * 50, 1)) == 50          # always makes progress

# ── 2. message boxes and the End dialog in the accessibility tree ───────────
tree = Tree(d)


def dialog_text(dialog):
    tree.build()
    root = tree.identity(dialog)
    nodes = [n for n in tree.nodes.values()
             if n["id"] == root or n["parent"] == root]
    return nodes, " ".join(n["name"] + " " + str(n.get("text", ""))
                           for n in nodes)


box = wm.msgbox(d, "Receipt", "Session 3fa9c2d41b7e6a05 has ended.\n\n"
                "Result: verified_absent", icon="info")
nodes, exposed = dialog_text(box)
assert "3fa9c2d41b7e6a05" in exposed and "verified_absent" in exposed, nodes
assert any(n["role"] == "label" for n in nodes), nodes
box.close()

# a word wider than the box is split instead of running off it
box = wm.msgbox(d, "Wide", "W" * 64)
lines = wm._wrap_text("W" * 64, T.FONT, 260)
assert "".join(lines) == "W" * 64 and len(lines) > 1
assert all(T.text_w(T.FONT, line) <= 260 for line in lines)
box.close()

win = P.PtySessions(d)
d.wm.add(win)
end = time.time() + 8
fake.set(F.standard_responses())
win.refresh()
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
win.list.sel = 1
win._select_session(win.list.items[1])
win._end()
dlg = H.find_window(d, "ConfirmEnd")
nodes, exposed = dialog_text(dlg)
assert F.DETACHED["id"] in exposed, nodes
assert F.DETACHED["command"] in exposed, nodes
assert "will be terminated" in exposed and "Cancel" in exposed, nodes
text_node = [n for n in nodes if n["role"] == "text"][0]
assert "read-only" in text_node["states"] and "editable" not in text_node["states"]
dlg.close()

# the receipt dialog
fake.set([F.kill_response(F.UNCERTAIN_UNSENT)] + F.standard_responses())
win._confirmed_end(F.DETACHED["id"], F.DETACHED["started_millis"])
end = time.time() + 8
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
receipt = [w for w in d.wm.windows if w.modal][-1]
nodes, exposed = dialog_text(receipt)
assert "uncertain" in exposed and "status_failed" in exposed, exposed
assert "Nothing was sent" in exposed, exposed
receipt.close()
win.close()

# ── 3. a read-only view is read-only everywhere ─────────────────────────────
view = P.OutputWindow(d, "Pane output: t", "untrusted pane output",
                      "original pane output\nsecond line")
d.wm.add(view)
tree.build()
node = tree.nodes[tree.identity(view.view)]
assert "read-only" in node["states"] and "editable" not in node["states"], node
assert view.view.read_only
before = view.view.text()
for kind, args in (("set_text", ["changed through accessibility"]),
                   ("insert_text", [0, "evil"]),
                   ("delete_text", [0, 8]),
                   ("cut_text", [0, 8]),
                   ("paste_text", [0])):
    d.clipboard = "pasted"
    assert not tree.apply(node["id"], kind, args), kind
    assert view.view.text() == before, (kind, view.view.text())
# navigation, selection and copying are still accessible actions
assert tree.apply(node["id"], "caret", [4])
assert tree.apply(node["id"], "selection", [0, 8])
d.clipboard = ""
assert tree.apply(node["id"], "copy_text", [0, 8])
assert d.clipboard == "original"
assert view.view.text() == before

# the keyboard, a paste and the direct API are refused too
view.set_focus(view.view)
for key in ("Backspace", "Delete", "Enter", "Tab", "x", "Z"):
    H.key(d, key)
H.key(d, "v", ctrl=True)
d.dispatch_paste("pasted text")
view.view.insert("direct")
assert view.view.text() == before, view.view.text()
H.key(d, "a", ctrl=True)                         # select all ...
d.clipboard = ""
H.key(d, "c", ctrl=True)                         # ... copy
assert d.clipboard == before, repr(d.clipboard)
d.clipboard = ""
H.key(d, "x", ctrl=True)                         # cut is only a copy here
assert d.clipboard == before and view.view.text() == before
H.key(d, "ArrowDown")
H.key(d, "End")
assert view.view.text() == before
view.close()

# the shared widget is read-only only where asked: editors still edit
d2 = H.make_desk()
pad = Notepad(d2, None)
d2.wm.add(pad)
tree2 = Tree(d2)
tree2.build()
pnode = tree2.nodes[tree2.identity(pad.ta)]
assert "editable" in pnode["states"] and "read-only" not in pnode["states"]
assert tree2.apply(pnode["id"], "set_text", ["still editable"])
assert pad.ta.text() == "still editable"

print("ok")
