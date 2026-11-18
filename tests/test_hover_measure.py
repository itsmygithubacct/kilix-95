"""Buttonless pointer motion over a text widget must not measure text.

A hover report over Notepad or WordPad reaches the text widget under the
pointer. Only a left press or a left drag places the caret, and finding the
caret's column measures one prefix of the line per character, so a hover
over a long line used to cost hundreds of measuring calls per report.
"""
import harness as H          # noqa: sets up sys.path for the imports below
import apps

LONG = "Pack my box with five dozen liquor jugs. " * 10      # 410 characters


# ── Notepad: hover over a long line measures nothing ────────────────────────
d = H.make_desk(size=(1024, 768))
d.draw_cursor = True
apps.open(d, "notepad", None)
np_win = H.find_window(d, "Notepad")
ta = np_win.ta
ta.set_text("short line\n" + LONG)
ta.cr, ta.cc = 1, 370
ta._reveal()
assert ta.hx > 0, "the long line must be scrolled for this test"
gx, gy = np_win.client_origin()
with H.Measures() as m:
    for step in range(20):          # rows below the text clamp to the long line
        H.move(d, gx + ta.x + 20 + step * 20, gy + ta.y + 3 + 4 * ta.LH, btn=0)
assert m.n == 0, ("hover over Notepad measured text", m.n)
assert (ta.cr, ta.cc) == (1, 370), ("hover moved the caret", ta.cr, ta.cc)

# a left press still places the caret where the column scan says
px = gx + ta.x + 120
want = ta._col_at(1, (px - gx - ta.x) - 4 + ta.hx)
H.press(d, px, gy + ta.y + 3 + ta.LH + 2)
assert (ta.cr, ta.cc) == (1, want), ("press column", ta.cr, ta.cc, want)
# and a left drag still moves it
px2 = gx + ta.x + 300
want2 = ta._col_at(1, (px2 - gx - ta.x) - 4 + ta.hx)
H.move(d, px2, gy + ta.y + 3 + ta.LH + 2, btn=1)
assert (ta.cr, ta.cc) == (1, want2), ("drag column", ta.cr, ta.cc, want2)
H.release(d, px2, gy + ta.y + 3 + ta.LH + 2)
assert ta.anchor == (1, want), ("drag selection anchor", ta.anchor)


# ── WordPad: hover measures nothing; press and drag still select ────────────
d2 = H.make_desk(size=(1024, 768))
apps.open(d2, "wordpad", None)
wp = H.find_window(d2, "WordPad")
rta = wp.rta
for ch in ("WordPad wraps this paragraph across several visual lines. " * 4):
    H.key(d2, ch)
wp.render()
wx, wy = wp.client_origin()
with H.Measures() as m:
    for step in range(20):
        H.move(d2, wx + rta.x + 10 + step * 15, wy + rta.y + 10, btn=0)
assert m.n == 0, ("hover over WordPad measured text", m.n)
H.press(d2, wx + rta.x + 12, wy + rta.y + 8)
start = rta.caret
assert rta.anchor == start, ("press anchor", rta.anchor, start)
H.move(d2, wx + rta.x + 200, wy + rta.y + 8, btn=1)
assert rta.caret != start, ("drag did not extend the selection", rta.caret)
H.release(d2, wx + rta.x + 200, wy + rta.y + 8)

print("ok")
