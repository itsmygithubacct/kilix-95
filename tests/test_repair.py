"""A partial repaint matches a full redraw, and a move composes."""
import harness  # noqa: F401
import main as desk_main
import wm


def _matches_full(desk):
    partial = desk.fb.tobytes()
    desk.dirty = True
    desk.render()
    return desk.fb.tobytes() == partial


def _count_full_draws(desk):
    draws = []
    real = desk.shell.draw

    def wrapped(fb, d):
        draws.append(1)
        return real(fb, d)

    desk.shell.draw = wrapped
    return draws


def test_a_window_move_repaints_only_the_strips():
    desk = desk_main.Desk(term=None, size=(640, 480))
    desk.render()
    win = wm.Window(desk, "Note", 180, 120, x=40, y=36)
    desk.wm.add(win)
    desk.render()
    before = desk.fb.tobytes()
    old = (win.x, win.y, win.w, win.h)
    draws = _count_full_draws(desk)
    win.x += 12
    desk.add_damage(*old)
    desk.add_damage(win.x, win.y, win.w, win.h)
    desk.render()
    assert not draws, "window move rebuilt the whole desk"
    assert _matches_full(desk), "partial move disagreed with a full redraw"
    plan = desk_main.frame_move(
        before, desk.fb.tobytes(), desk.w, desk.h,
        old, (win.x, win.y, win.w, win.h))
    assert plan is not None, "translation was not a compose"
    _source, _dest, residuals = plan
    assert sum(rect[2] * rect[3] for rect in residuals) < win.w * win.h


def test_a_clock_tick_repaints_the_clock():
    desk = desk_main.Desk(term=None, size=(640, 480))
    desk.render()
    desk.taskbar._minute = "not-a-time"
    draws = _count_full_draws(desk)
    desk.taskbar.tick(1)
    desk.render()
    assert desk.taskbar._minute != "not-a-time"
    assert not draws, "clock tick rebuilt the whole desk"
    assert _matches_full(desk), "clock repair disagreed with a full redraw"


def test_a_cursor_step_repaints_the_pointer():
    desk = desk_main.Desk(term=None, size=(640, 480), draw_cursor=True)
    desk.render()
    old = desk.mouse_pos
    desk.mouse_pos = (24, 30)
    draws = _count_full_draws(desk)
    desk.add_damage(*desk._cursor_box(*old))
    desk.add_damage(*desk._cursor_box(*desk.mouse_pos))
    desk.render()
    assert not draws, "cursor step rebuilt the whole desk"
    assert _matches_full(desk), "cursor repair disagreed with a full redraw"


def test_a_front_window_survives_repair_behind_it():
    desk = desk_main.Desk(term=None, size=(640, 480))
    desk.render()
    back = wm.Window(desk, "Back", 200, 160, x=30, y=30)
    front = wm.Window(desk, "Front", 90, 70, x=100, y=100)
    desk.wm.add(back)
    desk.wm.add(front)
    desk.render()
    draws = _count_full_draws(desk)
    # The icon cell around (40, 40) is larger than this nick, and the back
    # window shares that cell while covering the front window outside it.
    desk.add_damage(40, 40, 16, 16)
    desk.render()
    assert not draws, "a nick in one cell rebuilt the whole desk"
    assert _matches_full(desk), "repair covered the front window"


class _Term:
    def __init__(self):
        self.cols, self.rows = 20, 12
        self.cell_w, self.cell_h = 8, 8
        self.writes = []

    def write(self, data):
        self.writes.append(data)


def test_a_move_is_sent_as_one_compose():
    term = _Term()
    desk = desk_main.Desk(term=term)
    try:
        desk.render()
        win = wm.Window(desk, "Note", 40, 30, x=8, y=8)
        desk.wm.add(win)
        desk.render()
        sent_from = len(term.writes)
        old = (win.x, win.y, win.w, win.h)
        win.x += 6
        desk.add_damage(*old)
        desk.add_damage(win.x, win.y, win.w, win.h)
        desk.render()
        sent = "".join(term.writes[sent_from:])
        assert sent.startswith("\x1b[?2026h"), "compose was not one update"
        assert sent.endswith("\x1b[?2026l"), sent[-24:]
        assert "a=c," in sent and "N=2" in sent, "move did not compose"
        assert "a=f," in sent, "exposed strips were not uploaded"
        assert _matches_full(desk), "composed move disagreed with a full redraw"
    finally:
        desk.cleanup_shm()


test_a_window_move_repaints_only_the_strips()
test_a_clock_tick_repaints_the_clock()
test_a_cursor_step_repaints_the_pointer()
test_a_front_window_survives_repair_behind_it()
test_a_move_is_sent_as_one_compose()
print("ok")
