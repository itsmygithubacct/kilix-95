"""Backup and Restore applet: back up, restore, and restart without saving over it."""
import os
from unittest import mock

import harness as H
import widgets as W
from apps import controlpanel
from apps.backup import BackupWin


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
    raise AssertionError(f"no {label!r} in {win.title!r}")


assert ("Backup", "floppy", "backup", None) in controlpanel.CONTROL_ITEMS

d = H.make_desk()
import apps                                                   # noqa: E402
apps.open(d, "backup")
win = H.find_window(d, "BackupWin")
assert win is not None and win.backend is not None, "the host provides kilix_sdk.backup"

# Back Up Now writes a private archive holding the desktop documents.
desktop = d.shell.dir
with open(os.path.join(desktop, "letter.txt"), "w") as fh:
    fh.write("original\n")
win.back_up()
press(box(d, "Backup"), "OK")
archives = sorted(os.listdir(win.backend.default_directory()))
assert len(archives) == 1 and archives[0].endswith(".tar.gz"), archives
archive = os.path.join(win.backend.default_directory(), archives[0])

# Restore says what it will change, restores, and restarts under the supervisor
# without waiting for anyone to click OK; the restarted desktop shows the notice.
with open(os.path.join(desktop, "letter.txt"), "w") as fh:
    fh.write("edited after the backup\n")
win.confirm_restore(archive)
d.running = True
with mock.patch.dict(os.environ, {"KILIX_DESKTOP_SUPERVISED": "1"}):
    press(box(d, "Restore"), "Restore")
with open(os.path.join(desktop, "letter.txt")) as fh:
    assert fh.read() == "original\n", "the document came back"
assert d.exit_status == d.RESTART_STATUS == 75 and not d.running
assert d.shell.state_frozen, "the replaced state is never saved over the restore"
saves = []
d.shell.state_store.save_dict = lambda value: saves.append(value)
d.shell._save_state()
assert saves == [], "a frozen shell writes nothing"
import storage                                                # noqa: E402
notice = storage.state_dir(d.RESTORE_NOTICE)
assert os.path.exists(notice)
after = H.make_desk()
after._start_document_recovery()                  # the restarted desktop's startup
assert box(after, "Restore") is not None and not os.path.exists(notice)

# Without a supervisor it relaunches itself the old way instead of exiting 75 ...
os.environ.pop("KILIX_DESKTOP_SUPERVISED", None)
d2 = H.make_desk()
calls = []
d2.shell._restart_desktop = lambda: calls.append("relaunch") or True
d2.restart_after_restore("Restored 1 file(s).")
assert calls == ["relaunch"] and getattr(d2, "exit_status", 0) == 0
assert d2.shell.state_frozen
# ... and if that relaunch fails it keeps saving settings and says so.
d3 = H.make_desk()
d3.shell._restart_desktop = lambda: False
d3.restart_after_restore("Restored 1 file(s).")
assert not d3.shell.state_frozen, "a desktop that cannot restart must keep saving"
assert box(d3, "Restore") is not None and not os.path.exists(storage.state_dir(d3.RESTORE_NOTICE))

# A requested restart is not reported as a crash.
import doc_recovery                                           # noqa: E402
seen = []
with mock.patch.object(doc_recovery, "offer", lambda desk, reason=None: seen.append(reason)), \
        mock.patch.dict(os.environ, {"KILIX_DESKTOP_RESTARTED": "1",
                                     "KILIX_DESKTOP_LAST_STATUS": "75"}):
    H.make_desk()._start_document_recovery()
with mock.patch.object(doc_recovery, "offer", lambda desk, reason=None: seen.append(reason)), \
        mock.patch.dict(os.environ, {"KILIX_DESKTOP_RESTARTED": "1",
                                     "KILIX_DESKTOP_LAST_STATUS": "1"}):
    H.make_desk()._start_document_recovery()
assert seen[0] is None and "stopped unexpectedly" in seen[1], seen

# A corrupt archive is refused with a message, and nothing restarts.
bad = os.path.join(win.backend.default_directory(), "bad.tar.gz")
with open(bad, "wb") as fh:
    fh.write(b"not a backup")
d4 = H.make_desk()
apps.open(d4, "backup")
w4 = H.find_window(d4, "BackupWin")
w4.confirm_restore(bad)
assert box(d4, "Restore") is not None and not getattr(d4.shell, "state_frozen", False)

print("ok")
