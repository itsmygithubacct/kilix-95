"""kilix desktop — Backup and Restore: settings and desktop documents.

A front for the host's ``kilix backup``: Back Up Now writes a private
archive; Restore checks an archive, says what it will change, restores it
(keeping a safety copy of the replaced files) and restarts the desktop so the
restored settings are loaded instead of overwritten.
"""
import os

import filedialog
import theme as T
import widgets as W
import wm

_FILTERS = [("Kilix backups", "*.tar.gz"), ("All Files", "*.*")]


def _backend():
    try:
        from kilix_sdk import backup
    except ImportError:
        return None
    return backup


class BackupWin(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Backup and Restore", 420, 230, icon="floppy",
                         resizable=False)
        self.backend = _backend()
        lines = (
            "Saves your settings, the desktop's layout and choices,",
            "and the documents on your desktop to one private file.",
            "Restoring replaces only the files the backup holds and",
            "keeps a copy of everything it replaces.",
        )
        for i, text in enumerate(lines):
            self.add(W.Label(14, 14 + i * 16, text))
        self.b_backup = self.add(W.Button(14, 96, 130, 24, "Back Up Now",
                                          cb=self.back_up))
        self.b_restore = self.add(W.Button(154, 96, 130, 24, "Restore…",
                                           cb=self.choose_restore))
        self.status = self.add(W.Label(14, 136, "", font=T.SMALL, color=T.SHADOW))
        if self.backend is None:
            self.b_backup.enabled = self.b_restore.enabled = False
            self.status.text = "This Kilix host does not provide backups yet."

    def back_up(self):
        try:
            path = self.backend.create()
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Backup", f"The backup failed:\n{error}", icon="error")
            return
        self.status.text = "Saved " + os.path.basename(path)
        self.invalidate()
        wm.msgbox(self.desk, "Backup", f"Backup saved to\n{path}", icon="info")

    def choose_restore(self):
        os.makedirs(self.backend.default_directory(), mode=0o700, exist_ok=True)
        filedialog.open_file(self.desk, "Restore a Backup",
                             lambda p: p and self.confirm_restore(p),
                             start=self.backend.default_directory(),
                             filters=_FILTERS)

    def confirm_restore(self, archive):
        try:
            rows = self.backend.plan(archive)
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Restore", f"This backup cannot be restored:\n{error}",
                      icon="error")
            return
        new = sum(1 for _n, _d, action in rows if action == "create")
        changed = sum(1 for _n, _d, action in rows if action == "replace")
        if not new and not changed:
            wm.msgbox(self.desk, "Restore", "Everything in this backup is already current.",
                      icon="info")
            return

        def answer(ans):
            if ans == "Restore":
                self.restore(archive)
        wm.msgbox(self.desk, "Restore",
                  f"Restore {new} new and {changed} changed file(s)?\n"
                  "Your current files are backed up first, and the desktop "
                  "restarts to load the restored settings.",
                  icon="warn", buttons=("Restore", "Cancel"), cb=answer, default=1)

    def restore(self, archive):
        try:
            result = self.backend.restore(archive)
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Restore", f"The restore failed:\n{error}", icon="error")
            return
        self.desk.restart_after_restore(
            f"Restored {result['written']} file(s).\n"
            f"Previous files: {os.path.basename(result['safety'])}")
