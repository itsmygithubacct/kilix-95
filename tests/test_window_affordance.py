"""Drag handles and text that stays inside its box.

Headless: no Xvfb. An XPane is only a bare instance, enough to hit the
move cap and report a pointer zone.
"""
from types import SimpleNamespace

from PIL import Image

import harness as H
import theme as T
import widgets as W
import wm
from apps import xpane


def _ink(img, y, x0, x1, color):
    return [x for x in range(x0, x1) if img.getpixel((x, y)) == color]


# ── the title bar is a move handle; edges resize; a field is an I-beam ──────
d = H.make_desk()
win = wm.Window(d, "Notes", 360, 240)
d.wm.add(win)
title_y = win.y + T.BORDER + 4
H.move(d, win.x + 80, title_y)
assert d.pointer == "move", d.pointer
H.move(d, win.x + T.BORDER + 4, title_y)
assert d.pointer == "arrow", "the system icon is not a drag handle"
kind, x0, y0, x1, y1 = win._sysbuttons()[0]
H.move(d, win.x + (x0 + x1) // 2, win.y + (y0 + y1) // 2)
assert d.pointer == "arrow", d.pointer
H.move(d, win.x + 80, win.y + 1)
assert d.pointer == "n", d.pointer
H.move(d, win.x + win.w - 2, win.y + 80)
assert d.pointer == "e", d.pointer
win.add(W.Button(20, 30, 80, 24, "OK"))
win.add(W.TextField(20, 80, 120))
ox, oy = win.client_origin()
H.move(d, ox + 40, oy + 40)
assert d.pointer == "arrow", d.pointer
H.move(d, ox + 40, oy + 90)
assert d.pointer == "text", d.pointer
H.press(d, win.x + 80, title_y)
assert d.wm.drag and d.wm.drag[1] == "move", d.wm.drag
H.move(d, 12, 12, btn=1)
assert d.pointer == "move", d.pointer
H.release(d, 12, 12)
assert d.wm.drag is None

d.wm.toggle_maximize(win)
H.move(d, 120, T.BORDER + 4)
assert d.pointer == "arrow", d.pointer
H.press(d, 120, T.BORDER + 4)
H.release(d, 120, T.BORDER + 4)
assert d.wm.drag is None and win.maximized and (win.x, win.y) == (0, 0)


# ── three white ridges sit in the title, clear of the caption ───────────────
d = H.make_desk()
win = wm.Window(d, "Drag this window by its title", 360, 200)
d.wm.add(win)
win.invalidate()
img = win.render()
box = win._title_grip_box()
assert box, "a normal window should show a drag cue"
gx0, gy0, gx1, gy1 = box
mid = (gy0 + gy1) // 2
assert img.getpixel((gx0 + 1, mid)) == T.TITLE_A_TX
assert img.getpixel((gx0 + 3, mid)) == T.TITLE_A
d.wm.toggle_maximize(win)
assert win._title_grip_box() is None


# ── a long label wraps inside the client instead of running off the edge ────
d = H.make_desk()
win = wm.Window(d, "Copy", 240, 180)
text = ("alpha bravo charlie delta echo foxtrot golf hotel "
        "india juliet kilo lima")
win.add(W.Label(8, 10, text))
win.invalidate()
img = win.render()
cw, ch = win.client_size()
ox, oy = T.BORDER, T.BORDER + T.TITLE_H
first = _ink(img, oy + 14, ox, ox + cw, T.TEXT)
second = _ink(img, oy + 28, ox, ox + cw, T.TEXT)
assert first, "the first line did not paint"
assert second, "the label did not wrap onto a second line"
assert max(first) < ox + cw - 4 and max(second) < ox + cw - 4, (
    max(first), max(second), ox + cw)


# ── a narrow button ellipsizes instead of painting past its face ────────────
d = H.make_desk()
win = wm.Window(d, "Buttons", 260, 120)
btn = win.add(W.Button(8, 8, 70, 24, "Install the long name"))
win.invalidate()
img = win.render()
ox, oy = T.BORDER, T.BORDER + T.TITLE_H
xs = []
for y in range(oy + btn.y, oy + btn.y + btn.h):
    for x in range(ox, ox + win.client_size()[0]):
        if img.getpixel((x, y)) == T.TEXT:
            xs.append(x)
assert xs, "the button painted no caption"
assert min(xs) >= ox + btn.x and max(xs) < ox + btn.x + btn.w, (
    min(xs), max(xs), ox + btn.x, btn.w)


# ── icon names use the lines the cell can hold, each one inside the cell ───
grid = W.IconGrid(0, 0, 300, 400)
words = grid._wrap("alpha bravo charlie delta echo foxtrot golf hotel")
assert 2 <= len(words) <= 3, words
assert all(T.text_w(T.FONT, line) <= T.CELL_W - 6 for line in words), words
packed = grid._wrap("x" * 40)
assert 2 <= len(packed) <= 3, packed
assert all(T.text_w(T.FONT, line) <= T.CELL_W - 6 for line in packed), packed


# ── a menu wider than the desk is clamped, and its label is cut to fit ─────
d = H.make_desk((180, 200))
menu = d.menus.open([W.MenuItem("x" * 80)], 0, 0)
assert menu.w <= d.w - 4, menu.w


# ── the move cursor paints above the hotspot; the arrow does not ───────────
d = H.make_desk()
blank = Image.new("RGB", (40, 40), (0, 128, 128))
d.pointer = "arrow"
d.mouse_pos = (20, 20)
d._paint_cursor(W.drawer(blank))
assert blank.getpixel((20, 12)) == (0, 128, 128)
blank = Image.new("RGB", (40, 40), (0, 128, 128))
d.pointer = "move"
d._paint_cursor(W.drawer(blank))
assert blank.getpixel((20, 12)) != (0, 128, 128)
assert blank.getpixel((12, 20)) != (0, 128, 128)


# ── a hosted window's cap is a move handle even where the mask is clear ────
class _Rec:
    def __init__(self):
        self.drags = []
        self.maximized = []

    def begin_drag(self, win, mode, x, y):
        self.drags.append((mode, x, y))

    def toggle_maximize(self, win):
        self.maximized.append(win)


pane = object.__new__(xpane.XPane)
pane.x = pane.y = 0
pane.w, pane.h = 400, 300
pane.maximized = False
pane.resizable = True
pane.chromeless = True
pane.widgets = []
pane._capture = None
pane.compose_mask = Image.new("L", (400, 300), 0)
rec = _Rec()
pane.desk = SimpleNamespace(wm=rec)
assert pane.move_grip_rect() == (164, 0, 236, 10)
assert pane.hit_test(200, 9) is True
assert pane.compose_mask.getpixel((200, 40)) == 0
assert pane.hit_test(200, 40) is False
assert pane.pointer_zone(200, 4) == "move"
assert pane.pointer_zone(2, 2) == "nw"
assert pane.pointer_zone(200, 40) == "arrow"
pane.on_mouse(W.Ev(kind="mouse", x=200, y=4, btn=1, press=True, clicks=1))
assert rec.drags == [("move", 200, 4)], rec.drags
pane.maximized = True
assert pane.move_grip_rect() is None
assert pane.pointer_zone(200, 4) == "arrow"
assert pane.tooltip_at(200, 4) is None
pane.maximized = False
assert pane.tooltip_at(200, 4) == "Drag to move"
pane._reveal_move_grip()
assert pane.compose_mask.getpixel((200, 4)) == 255
assert pane.compose_mask.getpixel((200, 40)) == 0

print("ok")
