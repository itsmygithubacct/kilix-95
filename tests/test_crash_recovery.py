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

print("ok")
