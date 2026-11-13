"""Desktop and folder icon labels are measured once, not on every repaint.

The desktop repaints on every pointer report (it draws its own pointer), and
wrapping a label that does not fit its cell measures it once per character.
The grid keeps each label's lines and widths per font, cell width and label.
"""
import os

import harness as H          # noqa: sets up sys.path for the imports below
import theme as T
import widgets as W
from PIL import Image


# ── Icon grid: labels are measured once, then drawn from that layout ────────
def grid_image(grid, size=(320, 4 * T.CELL_H + 8)):
    img = Image.new("RGB", size, T.DESKTOP)
    grid.draw(W.drawer(img), img)
    return img.tobytes()


def reference(items, sel):
    """The same grid drawn by measuring every label on every draw."""
    ref = W.IconGrid(0, 0, 320, 4 * T.CELL_H + 4, desktop=True)
    ref._label_layout = lambda label: tuple(
        (ln, T.text_w(T.FONT, ln)) for ln in ref._wrap(label))
    ref.set_items([dict(it) for it in items])
    ref.sel = set(sel)
    return grid_image(ref)


items = [{"label": name, "icon": "doc"} for name in (
    "budget 2026.txt", "garden plan.txt", "letter to grandma.txt",
    "notes.txt", "a much longer file name than the cell can hold.txt")]
grid = W.IconGrid(0, 0, 320, 4 * T.CELL_H + 4, desktop=True)
grid.set_items(items)
grid.sel = {2}                      # a selected label draws its width as a box
first = grid_image(grid)
assert first == reference(items, {2}), "measured layout differs from measuring"
with H.Measures() as m:
    again = grid_image(grid)
assert m.n == 0, ("a repaint re-measured the labels", m.n)
assert again == first, "a repaint drew different pixels"

# a renamed item draws its new label
items[0]["label"] = "budget 2027 final.txt"
assert grid_image(grid) == reference(items, {2}), "a renamed label drew stale text"

# another font measures again instead of reusing the old widths
saved = T.FONT
try:
    T.FONT = T.BOLD
    assert grid_image(grid) == reference(items, {2}), \
        "a font change kept the previous font's label layout"
finally:
    T.FONT = saved
assert grid_image(grid) == reference(items, {2}), "back to the regular face"

# a new folder drops the old folder's labels
grid.set_items([{"label": "one.txt", "icon": "doc"},
                {"label": "two.txt", "icon": "doc"}])
grid_image(grid)
assert len(grid._label_layouts) == 2, ("old labels kept", len(grid._label_layouts))


# ── Desktop: the icon grid adds no measuring to a pointer report ────────────
with H.desktop_dir() as folder:
    for name in ("letter to grandma.txt", "meeting minutes.txt",
                 "trip itinerary.txt", "phone numbers.txt", "notes.txt"):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(name + "\n")
    d3 = H.make_desk(size=(1024, 768))
    d3.draw_cursor = True
    d3.shell.refresh()
    d3.render()
    assert any(len(d3.shell.grid._wrap(it["label"])) > 1
               for it in d3.shell.grid.items), "no wrapped label on the desktop"
    with H.Measures() as m:
        for step in range(10):
            H.move(d3, 300 + step * 7, 400 + step * 3, btn=0)
            d3.shell.draw(d3.fb, W.drawer(d3.fb))
    assert m.n == 0, ("desktop icon labels measured during hover", m.n)

print("ok")
