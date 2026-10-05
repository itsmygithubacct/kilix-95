"""Unsaved-document checkpoints, so a crash does not take the user's typing with it.

A window opts in by defining ``recovery_app`` (a name ``apps.open`` accepts),
``recovery_snapshot()`` (a JSON-serialisable dict) and ``recovery_restore(snap)``.
While such a window is ``modified`` its snapshot is written, at most once per
``INTERVAL`` seconds and only when it changed, to its own crash-safe record under
``state/document-recovery/``.  A save, a new or opened document (which clear
``modified``) or a deliberate close removes the record; a window closed because
it failed, or a desktop that dies, leaves it in place.  The next desktop start
offers every remaining record for restore, and names any it cannot restore.
"""

import json
import os
import time
import uuid

import durable_state
import storage

INTERVAL = 1.0                      # seconds between checkpoint passes
MAX_DOCUMENT = 8 * 1024 * 1024      # larger snapshots keep only a name-only marker
_DIRNAME = "document-recovery"
_MAX_PAYLOAD = 16 * 1024 * 1024


def _dir():
    path = storage.state_dir(_DIRNAME)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _store(token):
    return durable_state.JsonState(os.path.join(_DIRNAME, token),
                                   max_payload=_MAX_PAYLOAD)


def _token(win):
    token = getattr(win, "_recovery_token", None)
    if token is None:
        token = win._recovery_token = uuid.uuid4().hex
    return token


def _recoverable(win):
    return callable(getattr(win, "recovery_snapshot", None)) and getattr(
        win, "recovery_app", None)


def _name(win):
    path = getattr(win, "path", None)
    return os.path.basename(path) if path else "Untitled"


def write(win):
    """Checkpoint ``win`` now if its snapshot changed. Returns True when a record
    for its current unsaved state exists afterwards."""
    if not _recoverable(win) or not getattr(win, "modified", False):
        return False
    try:
        snap = win.recovery_snapshot()
        body = json.dumps(snap, sort_keys=True, ensure_ascii=True)
    except Exception:
        return False
    if body == getattr(win, "_recovery_written", None):
        return True
    record = {"app": win.recovery_app, "name": _name(win),
              "path": getattr(win, "path", None), "saved_at": time.time()}
    if len(body) > MAX_DOCUMENT:
        record["too_large"] = True
    else:
        record["snapshot"] = snap
    _dir()
    try:
        with _store(_token(win)) as store:
            store.save_dict(record)
    except (durable_state.StateError, OSError):
        return False
    win._recovery_written = body
    return not record.get("too_large", False)


def clear(win):
    """Remove ``win``'s checkpoint (saved, replaced or deliberately discarded)."""
    token = getattr(win, "_recovery_token", None)
    win._recovery_written = None
    if token is None:
        return
    for name in os.listdir(_dir()):
        if name == token or name.startswith(token + "."):
            try:
                os.unlink(os.path.join(_dir(), name))
            except OSError:
                pass


def tick(desk, now):
    """Desk tick hook: checkpoint modified windows, drop records of clean ones."""
    if now - getattr(desk, "_recovery_last", 0.0) < INTERVAL:
        return
    desk._recovery_last = now
    for win in list(desk.wm.windows):
        if not _recoverable(win):
            continue
        if getattr(win, "modified", False):
            write(win)
        elif getattr(win, "_recovery_written", None) is not None:
            clear(win)


def closed(win):
    """A window closed on purpose: its unsaved state was saved or discarded."""
    if _recoverable(win) and not getattr(win, "_recovery_fault", False):
        clear(win)


def pending():
    """[(token, record)] for every checkpoint left by an earlier failure."""
    out = []
    try:
        names = sorted(os.listdir(_dir()))
    except OSError:
        return out
    for token in names:
        if "." in token:             # the store's temporary/lock siblings
            continue
        with _store(token) as store:
            record = store.load_dict()
        if record.get("app"):
            out.append((token, record))
    return out


def _forget(token):
    for name in os.listdir(_dir()):
        if name == token or name.startswith(token + "."):
            try:
                os.unlink(os.path.join(_dir(), name))
            except OSError:
                pass


def restore(desk, token, record):
    """Reopen one checkpoint as an unsaved document; True on success."""
    import apps
    if record.get("too_large") or "snapshot" not in record:
        return False
    before = list(desk.wm.windows)
    apps.open(desk, record["app"], None)
    new = [w for w in desk.wm.windows if w not in before]
    if not new or not callable(getattr(new[-1], "recovery_restore", None)):
        return False
    win = new[-1]
    win.recovery_restore(record)
    # The reopened window owns the record now: write it under its own token
    # before forgetting the old one, so a second failure still keeps the text.
    write(win)
    _forget(token)
    return True


_APP_LABELS = {"notepad": "Notepad", "wordpad": "WordPad"}


def app_label(app):
    """The program's own name as the user sees it in its title bar."""
    return _APP_LABELS.get(app, app.title())


def offer(desk, items=None, reason=None):
    """Ask the user about pending checkpoints; nothing happens without an answer."""
    import wm
    items = pending() if items is None else items
    if not items:
        return
    names = []
    for _token_, record in items:
        label = f"{record.get('name', 'Untitled')} ({app_label(record['app'])})"
        if record.get("too_large"):
            label += " - too large to keep, changes lost"
        names.append("  " + label)
    restorable = [(t, r) for t, r in items if not r.get("too_large")]
    lost_only = not restorable
    text = (reason or "Unsaved documents were kept when a program stopped "
            "unexpectedly:") + "\n\n" + "\n".join(names)
    if lost_only:
        wm.msgbox(desk, "Document Recovery", text, icon="warn",
                  cb=lambda _ans: [_forget(t) for t, _r in items])
        return

    def answer(ans):
        if ans == "Restore":
            for token, record in items:
                if record.get("too_large"):
                    _forget(token)
                elif not restore(desk, token, record):
                    pass             # stays pending for the next start
        elif ans == "Discard":
            for token, _record in items:
                _forget(token)
    wm.msgbox(desk, "Document Recovery", text + "\n\nRestore them now?",
              icon="warn", buttons=("Restore", "Later", "Discard"), cb=answer)
