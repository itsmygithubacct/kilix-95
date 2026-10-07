"""kilix desktop — PTY Sessions (Win95-style manager for persistent panes).

Lists the sessions kitty-pty-broker keeps alive behind Kilix panes, shows one
in detail, observes it read-only, attaches a detached one, ends one with a
confirmation and a truthful receipt, and browses the archived journals of
sessions that are gone.

Everything comes from the `kilix pty ... --json` contract (schema
``kilix.pty/v1``); the broker, its sockets and its files are never touched
here. Text read from a session is untrusted data: it is shown, never executed,
and control characters are neutralised before it reaches a widget. Every
subprocess runs on a worker thread and is polled from a tick hook, like Task
Manager's refresh and Help Search's lookup, so a wedged broker cannot freeze
the desktop.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import time

import icons
import theme as T
import widgets as W
import wm

from apps.helpsearch import kilix_launcher
from apps.manual import _ReadOnlyTextArea

SCHEMA = "kilix.pty/v1"
RECEIPT_RESULTS = ("verified_absent", "uncertain", "not_found", "refused")
# The exit status each receipt result must arrive with (CONTRACT: exit table).
RECEIPT_EXIT = {"verified_absent": 0, "uncertain": 1, "refused": 3,
                "not_found": 4}
VIEW_LINES = 200                  # a snapshot is the last N lines ...
VIEW_CHARS = 64 * 1024            # ... and never more than this much text
JSON_LIMIT = 4 * 1024 * 1024      # refuse a stdout larger than this
LIST_TIMEOUT = 20                 # seconds; kilix itself bounds each broker call
VIEW_TIMEOUT = 30
KILL_TIMEOUT = 60                 # grace period + verification polling + guard
REFRESH_SECONDS = 5.0
COMMAND_LIMIT = 240               # characters of the command the dialog shows

_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
_CONTROLS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f"
                       "\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_SINGLE = re.compile("[\x00-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]")

M = 8
TAB_Y = 4
HEAD_Y = 30
HEAD_H = 16
BTN_H = 24
STATUS_H = 20
DETAIL_H = 150


class PtyError(Exception):
    """A `kilix pty` call that gave no usable answer; the text is user-facing."""


# ── pure helpers ─────────────────────────────────────────────────────────────

def valid_id(value):
    """A session ID the broker accepts: [A-Za-z0-9._-]{1,64}, not . or .."""
    return (isinstance(value, str) and value not in (".", "..")
            and _ID_RE.fullmatch(value) is not None)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def clean_text(value, multiline=False, limit=None):
    """Text from a session, made safe to draw: no escapes, no bidi overrides."""
    text = "" if value is None else str(value)
    if multiline:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _CONTROLS.sub("?", text)
    else:
        text = _SINGLE.sub(" ", text)
    if limit is not None and len(text) > limit:
        text = text[:limit - 1] + "…"
    return text


def own_session_id(environ=None):
    """The broker session this desktop itself runs in, if any."""
    value = (os.environ if environ is None else environ).get(
        "KITTY_PTY_BROKER_SESSION")
    return value or None


def format_age(started_millis, now_millis):
    if not _is_int(started_millis) or not _is_int(now_millis):
        return "?"
    seconds = max(0, (now_millis - started_millis) // 1000)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h {minutes:02d}m"
    return f"{hours // 24}d {hours % 24}h"


def format_bytes(count):
    if not _is_int(count):
        return "?"
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def format_time(millis):
    if not _is_int(millis):
        return "unknown"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(millis / 1000))
    except (OverflowError, OSError, ValueError):
        return "unknown"


def session_state(session):
    if session.get("reachable") is False:
        return "unreachable"
    return "attached" if session.get("attached") else "detached"


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


# ── the kilix pty contract ───────────────────────────────────────────────────

def run_pty(args, launcher=None, timeout=LIST_TIMEOUT):
    """Run `kilix pty ARGS...`; return (exit status, JSON document|None, stderr).

    A document, when there is one, is checked against the schema marker. The
    command not starting, not answering in time, or printing something that is
    not the contract is a PtyError; a non-zero status with a valid document
    (kill receipts, not_found) is returned to the caller to interpret.
    """
    launcher = launcher or kilix_launcher()
    if launcher is None:
        raise PtyError("The Kilix launcher is unavailable.")
    try:
        done = subprocess.run([launcher, "pty", *args], capture_output=True,
                              text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise PtyError(f"kilix pty did not answer within {timeout} seconds.") \
            from error
    except OSError as error:
        raise PtyError(f"Could not start kilix pty: {error}") from error
    stdout = done.stdout or ""
    stderr = clean_text((done.stderr or "").strip().splitlines()[-1]
                        if (done.stderr or "").strip() else "", limit=300)
    if not stdout.strip():
        return done.returncode, None, stderr
    if len(stdout) > JSON_LIMIT:
        raise PtyError("kilix pty returned more data than expected.")
    try:
        doc = json.loads(stdout)
    except ValueError as error:
        raise PtyError("kilix pty returned something that is not JSON.") \
            from error
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise PtyError(f"kilix pty returned an unknown schema "
                       f"(expected {SCHEMA}).")
    return done.returncode, doc, stderr


def _expect_document(code, doc, stderr, what):
    if doc is None:
        raise PtyError(stderr or f"{what} failed (exit status {code}).")
    return doc


def load_sessions(launcher=None):
    """`kilix pty list --json` → {"runtime", "sessions", "unreachable"} rows."""
    code, doc, stderr = run_pty(["list", "--json"], launcher)
    doc = _expect_document(code, doc, stderr, "Listing sessions")
    if code != 0:
        raise PtyError(stderr or f"Listing sessions failed (exit status {code}).")
    sessions, unreachable = doc.get("sessions"), doc.get("unreachable")
    if not isinstance(sessions, list) or not isinstance(unreachable, list) \
            or any(not isinstance(item, dict) or not isinstance(
                item.get("id"), str) for item in sessions + unreachable):
        raise PtyError("kilix pty list returned a malformed session list.")
    return {"runtime": clean_text(doc.get("runtime")),
            "sessions": [dict(item) for item in sessions],
            "unreachable": [dict(item, reachable=False) for item in unreachable]}


def load_journals(launcher=None):
    """`kilix pty journals list --json` → {"runtime", "journals"}."""
    code, doc, stderr = run_pty(["journals", "list", "--json"], launcher)
    doc = _expect_document(code, doc, stderr, "Listing journals")
    if code != 0:
        raise PtyError(stderr or f"Listing journals failed (exit status {code}).")
    journals = doc.get("journals")
    if not isinstance(journals, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str)
            for item in journals):
        raise PtyError("kilix pty journals returned a malformed list.")
    return {"runtime": clean_text(doc.get("runtime")),
            "journals": [dict(item) for item in journals]}


def _bounded_text(doc, what):
    text = doc.get("text")
    if not isinstance(text, str):
        raise PtyError(f"{what} came back without text.")
    text = clean_text(text, multiline=True)
    lines = text.split("\n")
    cut = bool(doc.get("truncated"))
    if len(lines) > VIEW_LINES + 1:
        lines, cut = lines[-(VIEW_LINES + 1):], True
    text = "\n".join(lines)
    if len(text) > VIEW_CHARS:
        text, cut = text[-VIEW_CHARS:], True
    total = doc.get("total_bytes")
    return {"text": text, "truncated": cut,
            "total_bytes": total if _is_int(total) else None}


def _view(args, wanted_id, what, launcher):
    code, doc, stderr = run_pty(args, launcher, VIEW_TIMEOUT)
    doc = _expect_document(code, doc, stderr, what)
    if code != 0:
        raise PtyError(stderr or f"{what} failed (exit status {code}).")
    if doc.get("id") != wanted_id:
        raise PtyError(f"{what} answered for a different session.")
    return _bounded_text(doc, what)


def fetch_pane_text(session_id, launcher=None):
    """A bounded read-only snapshot: `observe ID --once --text` (as JSON)."""
    if not valid_id(session_id):
        raise PtyError("That session ID is not usable.")
    return _view(["observe", session_id, "--once", "--lines", str(VIEW_LINES),
                  "--text", "--json"], session_id, "The snapshot", launcher)


def fetch_journal_text(journal_id, started_millis, launcher=None):
    """A bounded text rendering of an archived journal."""
    if not valid_id(journal_id):
        raise PtyError("That journal ID is not usable.")
    ref = f"{journal_id}.{started_millis}" if _is_int(started_millis) \
        else journal_id
    return _view(["journals", "show", ref, "--text", "--json",
                  "--lines", str(VIEW_LINES)], journal_id, "The journal",
                 launcher)


def can_end(session, own=None):
    """(allowed, reason): may this listed session be ended from here?"""
    if session_state(session) == "unreachable":
        return False, ("It is not answering, so its start time is unknown "
                       "and an end request cannot be bound to it.")
    if not valid_id(session.get("id")):
        return False, "Its ID is not one the broker accepts."
    if own is not None and session.get("id") == own:
        return False, "This desktop is running in this session."
    if not _is_int(session.get("started_millis")):
        return False, "Its start time is unknown."
    return True, ""


def end_session(session_id, started_millis, launcher=None, own=None):
    """End one session and return its receipt as a dict.

    The receipt's "result" is one of kilix's four (verified_absent, uncertain,
    not_found, refused) or "no_receipt" when kilix gave no valid receipt — in
    which case nobody can say whether the session ended.
    """
    base = {"id": session_id, "started_millis": started_millis}
    if own is not None and session_id == own:
        return dict(base, result="refused", reason="own_session",
                    request_sent=False, local=True,
                    message="This desktop is running in this session.")
    if not valid_id(session_id) or not _is_int(started_millis):
        return dict(base, result="no_receipt", request_sent=False,
                    message="The session cannot be named exactly.")
    try:
        code, doc, stderr = run_pty(
            ["kill", session_id, "--yes", "--expect-started",
             str(started_millis), "--json"], launcher, KILL_TIMEOUT)
    except PtyError as error:
        return dict(base, result="no_receipt", message=str(error))
    result = doc.get("result") if doc else None
    if result not in RECEIPT_RESULTS or doc.get("id") != session_id \
            or RECEIPT_EXIT[result] != code:
        return dict(base, result="no_receipt", message=stderr or
                    f"kilix pty kill gave no valid receipt (exit status {code}).")
    return dict(base, result=result, reason=doc.get("reason"),
                request_sent=doc.get("request_sent"),
                message=clean_text(doc.get("message"), limit=200),
                waited_ms=doc.get("waited_ms"))


def receipt_message(receipt):
    """(icon, text) telling exactly what the receipt established."""
    sid = clean_text(receipt.get("id"))
    result = receipt.get("result")
    reason = clean_text(receipt.get("reason"))
    detail = clean_text(receipt.get("message"))
    sent = receipt.get("request_sent")
    if result == "verified_absent":
        waited = receipt.get("waited_ms")
        after = f" (checked for {waited} ms)" if _is_int(waited) else ""
        return "info", (f"Session {sid} has ended.\n\nResult: verified_absent\n"
                        f"The broker no longer lists it{after}.")
    if result == "uncertain":
        said = ("The end request WAS sent, but the session's absence could "
                "not be verified." if sent else
                "The end request was NOT sent: the session could not be "
                "looked up.")
        return "warn", (f"Session {sid}: uncertain.\n\nResult: uncertain"
                        f"{' (' + reason + ')' if reason else ''}\n{said}\n"
                        "Refresh the list before trying again.")
    if result == "not_found":
        return "warn", (f"Session {sid} was not found.\n\nResult: not_found\n"
                        "Nothing was ended; it may already be gone.")
    if result == "refused":
        return "warn", (f"Session {sid} was not ended.\n\nResult: refused"
                        f"{' (' + reason + ')' if reason else ''}\n"
                        f"{detail or 'The request was refused.'}\n"
                        "Nothing was ended.")
    return "error", (f"No receipt for session {sid}.\n\n{detail}\n"
                     "The session may or may not have ended. Refresh the "
                     "list to find out.")


# ── rows ─────────────────────────────────────────────────────────────────────

def session_row(session, now_millis):
    """A list row: (icon, accessible text, data) with the cells to draw."""
    state = session_state(session)
    sid = clean_text(session.get("id"), limit=64)
    if state == "unreachable":
        error = clean_text(session.get("error"), limit=40) or "no answer"
        cells = (sid, "UNREACHABLE", "?", "?", f"(not answering: {error})", "")
        label = f"{sid}, UNREACHABLE, not answering: {error}"
        icon = "warn"
    else:
        age = format_age(session.get("started_millis"), now_millis)
        size = (f"{session['columns']}x{session['rows']}"
                if _is_int(session.get("columns")) and _is_int(session.get("rows"))
                else "?")
        command = clean_text(session.get("command"), limit=300)
        cwd = clean_text(session.get("cwd_now") or "", limit=300)
        cells = (sid, state, age, size, command, cwd)
        label = (f"{sid}, {state}, age {age}, size {size}, {command}, "
                 f"in {cwd or 'an unknown directory'}")
        icon = "ptysessions"
    return (icon, label, {"session": session, "state": state, "cells": cells})


def journal_row(journal):
    jid = clean_text(journal.get("id"), limit=64)
    started = format_time(journal.get("started_millis"))
    raw = format_bytes(journal.get("raw_bytes"))
    packed = format_bytes(journal.get("compressed_bytes"))
    archived = format_time(journal.get("archived_millis"))
    cells = (jid, started, raw, packed, archived)
    label = (f"{jid}, started {started}, {raw} raw, {packed} archived, "
             f"archived {archived}")
    return ("doc_text", label, {"journal": journal, "cells": cells})


def session_details(row, runtime, own, now_millis):
    """The Details pane text for one list row."""
    session, state = row["session"], row["state"]
    lines = [f"Session: {clean_text(session.get('id'))}",
             f"State: {state}"]
    if state == "unreachable":
        lines += [
            f"Error: {clean_text(session.get('error')) or 'no answer'}",
            f"Runtime: {runtime or 'unknown'}",
            "",
            "This session's broker did not answer, so it may be wedged or",
            "gone. It is listed because it exists. Its command, size and start",
            "time are unknown, so Observe, Attach and End Session are",
            "unavailable. Refresh to ask again."]
        return "\n".join(lines) + "\n"
    started = session.get("started_millis")
    lines += [
        f"Started: {format_time(started)}"
        f" ({format_age(started, now_millis)} ago)",
        f"Size: {session.get('columns')} columns x "
        f"{session.get('rows')} rows",
        f"Command: {clean_text(session.get('command'))}",
        f"Started in: {clean_text(session.get('cwd'))}",
        f"Now in: "
        f"{clean_text(session.get('cwd_now')) or '(not available)'}",
        f"Broker pid: {session.get('broker_pid')}",
        f"Child pid: {session.get('child_pid')}"
        f"   (foreground group {session.get('foreground_pgrp')})",
        f"Journal: {format_bytes(session.get('journal_bytes'))}, epoch "
        f"{session.get('journal_epoch')}, replay "
        f"{'complete' if session.get('replay_complete') else 'incomplete'}",
        f"Boot id: {clean_text(session.get('boot_id')) or '(unknown)'}",
        f"Start ticks: "
        f"{'(unknown)' if session.get('start_ticks') is None else session['start_ticks']}",
        f"Runtime: {runtime or 'unknown'}",
        ""]
    if own is not None and session.get("id") == own:
        lines.append("This is the session this desktop runs in: it cannot "
                     "be ended from here.")
    elif state == "attached":
        lines.append("A client is attached, so it can be observed but not "
                     "attached.")
    else:
        lines.append("Nothing is attached; it can be observed or attached.")
    return "\n".join(lines) + "\n"


def journal_details(row, runtime):
    journal = row["journal"]
    return "\n".join([
        f"Session: {clean_text(journal.get('id'))}",
        f"Started: {format_time(journal.get('started_millis'))}",
        f"Ended: {format_time(journal.get('reaped_millis'))}",
        f"Archived: {format_time(journal.get('archived_millis'))}",
        f"Raw size: {format_bytes(journal.get('raw_bytes'))}",
        f"Archived size: {format_bytes(journal.get('compressed_bytes'))}",
        f"Broker pid: {journal.get('broker_pid')}",
        f"Child pid: {journal.get('child_pid')}",
        f"Archive file: {clean_text(journal.get('path'))}",
        f"Runtime: {runtime or 'unknown'}",
        "",
        "View Journal shows a bounded text rendering of what the pane",
        "displayed; the raw terminal bytes stay in the archive."]) + "\n"


# ── widgets ──────────────────────────────────────────────────────────────────

class _Viewer(_ReadOnlyTextArea):
    """Read-only text that wraps to its width without losing a character."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = ""

    def show(self, source, keep_scroll=False):
        pos = self.sb.pos
        self.source = source
        width = max(1, self.w - T.SCROLL_W - 10)
        lines = []
        for original in source.expandtabs(4).split("\n"):
            line = original
            while line and T.text_w(self.font, line) > width:
                low, high = 1, len(line)
                while low < high:
                    middle = (low + high + 1) // 2
                    if T.text_w(self.font, line[:middle]) <= width:
                        low = middle
                    else:
                        high = middle - 1
                lines.append(line[:max(1, low)])
                line = line[max(1, low):]
            lines.append(line)
        self.set_text("\n".join(lines))
        if keep_scroll:
            self.sb.pos = pos
            self.sb.total, self.sb.page = len(self.lines), self._rows()
            self.sb.clamp()


class _ColumnList(W.ListBox):
    """A ListBox whose rows are columns. Items are (icon, accessible text,
    data) as for ListBox; data["cells"] holds the strings to draw."""
    GUTTER = 24

    def __init__(self, x, y, w, h, columns, **kwargs):
        super().__init__(x, y, w, h, **kwargs)
        self.columns = columns                      # [(title, pixels|None)]

    def spans(self):
        """[(x offset from the list's left edge, width)] for each column."""
        avail = self.w - self.GUTTER - T.SCROLL_W - 8
        fixed = sum(width for _, width in self.columns if width)
        flex = [c for c in self.columns if not c[1]]
        share = max(40, (avail - fixed) // max(1, len(flex)))
        out, x = [], self.GUTTER
        for _, width in self.columns:
            width = width or share
            out.append((x, width))
            x += width
        return out

    def replace(self, items):
        """Swap the rows, keeping the selected row (by data["key"]) selected
        and the list scrolled where it was — a refresh must not move either."""
        chosen = (self.items[self.sel][2].get("key")
                  if 0 <= self.sel < len(self.items) else None)
        pos = self.sb.pos
        self.set_items(items)
        self.sb.pos = pos
        self.sel = -1
        for index, item in enumerate(items):
            if chosen is not None and item[2].get("key") == chosen:
                self.sel = index
        self.sb.total, self.sb.page = len(items), self._rows()
        self.sb.clamp()

    def draw(self, d, img):
        x0, y0 = self.x, self.y
        x1, y1 = x0 + self.w - 1, y0 + self.h - 1
        T.sunken(d, x0, y0, x1, y1)
        self.sb.total, self.sb.page = len(self.items), self._rows()
        self.sb.clamp()
        self.sb.place(x1 - T.SCROLL_W - 1, y0 + 2, self.h - 4)
        scrolls = self.sb.total > self.sb.page
        spans = self.spans()
        for i in range(self._rows()):
            idx = self.sb.pos + i
            if idx >= len(self.items):
                break
            icon, _, data = self.items[idx]
            yy = y0 + 2 + i * self.RH
            chosen = idx == self.sel
            if chosen:
                d.rectangle([x0 + 2, yy, x1 - 2 - (T.SCROLL_W if scrolls else 0),
                             yy + self.RH - 1], fill=T.SEL_BG)
            if icon:
                icons.paint(img, icon, x0 + 4, yy, 16)
            bold = data.get("state") == "unreachable"
            font = T.BOLD if bold else T.FONT
            for (cx, width), text in zip(spans, data["cells"]):
                d.text((x0 + cx, yy + 2),
                       T.ellipsize(font, text, max(8, width - 6)), font=font,
                       fill=T.SEL_TX if chosen else T.TEXT)
        if scrolls:
            self.sb.draw(d)


def _wrap_px(text, width):
    """Break text into lines of at most `width` pixels (a long word is split)."""
    lines = []
    for original in text.split("\n"):
        line = original
        while line and T.text_w(T.FONT, line) > width:
            low, high = 1, len(line)
            while low < high:
                middle = (low + high + 1) // 2
                if T.text_w(T.FONT, line[:middle]) <= width:
                    low = middle
                else:
                    high = middle - 1
            cut = max(1, low)
            space = line.rfind(" ", 0, cut)
            if space > 0 and cut < len(line):
                cut = space
            lines.append(line[:cut].rstrip())
            line = line[cut:].lstrip(" ")
        lines.append(line)
    return "\n".join(lines)


class OutputWindow(wm.Window):
    """Read-only text taken from a pane or a journal, labelled as such."""

    def __init__(self, desk, title, banner, text, icon="doc_text"):
        super().__init__(desk, title, 620, 420, icon=icon)
        self.min_w, self.min_h = 360, 240
        cw, ch = self.client_size()
        self.banner = banner
        self.view = self.add(_Viewer(M, 46, cw - 2 * M, ch - 46 - M, ""))
        self.view.accessibility_name = "Pane output (read-only, untrusted)"
        self.view.show(text)
        self.set_focus(self.view)

    def on_resize(self):
        cw, ch = self.client_size()
        self.view.w, self.view.h = cw - 2 * M, ch - 46 - M
        self.view.show(self.view.source)

    def draw_client(self, d, img):
        for i, line in enumerate(self.banner.split("\n")[:3]):
            d.text((M, 6 + i * 13), T.ellipsize(
                T.SMALL, line, self.client_size()[0] - 2 * M),
                font=T.SMALL, fill=T.TEXT)


# ── the window ───────────────────────────────────────────────────────────────

SESSION_COLUMNS = [("ID", 124), ("State", 104), ("Age", 54), ("Size", 52),
                   ("Command", None), ("Directory", None)]
JOURNAL_COLUMNS = [("Session", 140), ("Started", 150), ("Raw", 80),
                   ("Archived", 80), ("Archived at", None)]


class PtySessions(wm.Window):
    open_name = "ptysessions"
    label = "PTY Sessions"

    def __init__(self, desk, arg=None):
        super().__init__(desk, "PTY Sessions", 720, 540, icon="ptysessions")
        self.min_w, self.min_h = 700, 400
        cw, ch = self.client_size()
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.page = 0
        self.runtime = ""
        self.listed_at = None                # millis of the displayed listing
        self.session_status = self.session_summary = "Reading sessions…"
        self.journal_status = self.journal_summary = \
            "Open this page to read the archive."
        self.journals_loaded = False
        self.futures = {}                    # kind -> (future, context)
        self.last_refresh = time.time()
        self.closing = False

        self.tabs = self.add(W.TabBar(M, TAB_Y, cw - 2 * M,
                                      ["Sessions", "Archived Journals"],
                                      cb=self._switch))
        self.panels = ([], [])

        self.list = self._add(0, _ColumnList(
            M, 0, 0, 0, SESSION_COLUMNS, on_select=self._select_session,
            on_activate=lambda item: self._observe()))
        self.list.accessibility_name = "PTY sessions"
        self.details = self._add(0, _Viewer(M, 0, 0, 0, ""))
        self.details.accessibility_name = "Session details"
        self.b_refresh = self._add(0, W.Button(
            M, 0, 96, BTN_H, "Refresh", cb=self.refresh))
        self.b_observe = self._add(0, W.Button(
            0, 0, 96, BTN_H, "Observe", cb=self._observe, default=True))
        self.b_preview = self._add(0, W.Button(
            0, 0, 96, BTN_H, "Preview", cb=self._preview))
        self.b_attach = self._add(0, W.Button(
            0, 0, 96, BTN_H, "Attach", cb=self._attach))
        self.b_end = self._add(0, W.Button(
            0, 0, 120, BTN_H, "End Session…", cb=self._end))

        self.b_terminal = self._add(0, W.Button(
            0, 0, 130, BTN_H, "Open in Terminal", cb=self._open_terminal))

        self.jlist = self._add(1, _ColumnList(
            M, 0, 0, 0, JOURNAL_COLUMNS, on_select=self._select_journal,
            on_activate=lambda item: self._view_journal()))
        self.jlist.accessibility_name = "Archived journals"
        self.jdetails = self._add(1, _Viewer(M, 0, 0, 0, ""))
        self.jdetails.accessibility_name = "Journal details"
        self.b_jrefresh = self._add(1, W.Button(
            M, 0, 96, BTN_H, "Refresh", cb=self.refresh_journals))
        self.b_jview = self._add(1, W.Button(
            0, 0, 120, BTN_H, "View Journal…", cb=self._view_journal,
            default=True))
        self.b_jterminal = self._add(1, W.Button(
            0, 0, 130, BTN_H, "Open in Terminal", cb=self._open_terminal))
        for button, name in ((self.b_refresh, "Refresh sessions"),
                             (self.b_jrefresh, "Refresh journals")):
            button.accessibility_name = name

        self.on_close = self._cleanup
        desk.tick_hooks.append(self._tick)
        self._layout()
        self._switch(0)
        self._show_selected()
        self._show_selected_journal()
        self.refresh()

    def _add(self, page, widget):
        self.panels[page].append(self.add(widget))
        return widget

    # ── geometry ─────────────────────────────────────────────────────────────
    def _layout(self):
        cw, ch = self.client_size()
        self.tabs.w = cw - 2 * M
        btn_y = ch - STATUS_H - 6 - BTN_H - 2
        det_y = btn_y - 6 - DETAIL_H
        list_y = HEAD_Y + HEAD_H
        list_h = max(40, det_y - 6 - list_y)
        for lst, det in ((self.list, self.details), (self.jlist, self.jdetails)):
            lst.x, lst.y, lst.w, lst.h = M, list_y, cw - 2 * M, list_h
            det.x, det.y, det.w, det.h = M, det_y, cw - 2 * M, DETAIL_H
        x = M
        for button in (self.b_refresh, self.b_observe, self.b_preview,
                       self.b_attach, self.b_end, self.b_terminal):
            button.x, button.y = x, btn_y
            x += button.w + 8
        x = M
        for button in (self.b_jrefresh, self.b_jview, self.b_jterminal):
            button.x, button.y = x, btn_y
            x += button.w + 8

    def on_resize(self):
        self._layout()
        self.details.show(self.details.source, keep_scroll=True)
        self.jdetails.show(self.jdetails.source, keep_scroll=True)

    def _switch(self, index):
        self.page = index
        self.tabs.active = index
        for panel_index, panel in enumerate(self.panels):
            for widget in panel:
                widget.visible = panel_index == index
        focus = self.list if index == 0 else self.jlist
        self.set_focus(focus)
        if index == 1 and not self.journals_loaded:
            self.refresh_journals()
        self._sync_buttons()
        self.invalidate()

    # ── jobs: every kilix call runs off the UI thread ────────────────────────
    def _submit(self, kind, fn, *args, ctx=None, **kwargs):
        if kind in self.futures:
            return False
        self.futures[kind] = (self.pool.submit(fn, *args, **kwargs), ctx or {})
        self._sync_buttons()
        return True

    def _tick(self, now):
        for kind in list(self.futures):
            future, context = self.futures[kind]
            if future.done():
                del self.futures[kind]
                self._finish(kind, future, context)
        if (self.page == 0 and "list" not in self.futures
                and "kill" not in self.futures
                and now - self.last_refresh >= REFRESH_SECONDS):
            self.refresh()

    def _finish(self, kind, future, context):
        try:
            result = future.result()
        except PtyError as error:
            result, failure = None, str(error)
        except Exception as error:               # a worker must never be fatal
            result, failure = None, f"Unexpected failure: {error}"
        else:
            failure = None
        getattr(self, "_done_" + kind)(result, failure, context)
        self._sync_buttons()
        self.invalidate()

    def refresh(self):
        self.last_refresh = time.time()
        self._submit("list", load_sessions)

    def refresh_journals(self):
        self.journal_status = "Reading the archive…"
        self._submit("journals", load_journals)
        self.invalidate()

    # ── results ──────────────────────────────────────────────────────────────
    def _done_list(self, result, failure, context):
        self.last_refresh = time.time()
        if failure is not None:
            # Keep the last listing on screen but say it is stale: an error
            # must not make live sessions look absent, nor look current.
            stale = (f" Showing the list from {format_time(self.listed_at)}."
                     if self.listed_at else "")
            self.session_status = f"Could not list sessions: {failure}{stale}"
            return
        self.runtime = result["runtime"]
        self.listed_at = int(time.time() * 1000)
        reachable = sorted(result["sessions"], key=lambda s: (
            s.get("started_millis") if _is_int(s.get("started_millis")) else 0,
            s.get("id")), reverse=True)
        rows = [session_row(s, self.listed_at) for s in reachable] \
            + [session_row(s, self.listed_at) for s in result["unreachable"]]
        for item in rows:
            item[2]["key"] = self._key(item[2]["session"])
        self.list.replace(rows)
        self._show_selected()
        attached = sum(1 for r in rows if r[2]["state"] == "attached")
        detached = sum(1 for r in rows if r[2]["state"] == "detached")
        down = sum(1 for r in rows if r[2]["state"] == "unreachable")
        self.session_status = self.session_summary = (
            f"{_plural(len(rows), 'session')}: {attached} attached, "
            f"{detached} detached, {down} unreachable")

    def _done_journals(self, result, failure, context):
        if failure is not None:
            self.journal_status = f"Could not list journals: {failure}"
            return
        self.journals_loaded = True
        self.runtime = result["runtime"] or self.runtime
        rows = [journal_row(j) for j in result["journals"]]
        for item in rows:
            item[2]["key"] = self._key(item[2]["journal"])
        self.jlist.replace(rows)
        self._show_selected_journal()
        self.journal_status = self.journal_summary = (
            f"{_plural(len(rows), 'archived journal')}"
            if rows else "No archived journals.")

    def _done_preview(self, result, failure, context):
        sid = context["id"]
        self.session_status = self.session_summary
        if failure is not None:
            wm.msgbox(self.desk, "Preview",
                      f"Could not read session {sid}:\n{failure}", icon="error")
            return
        cut = (f"Only the last {VIEW_LINES} lines are shown; earlier output "
               "was cut.") if result["truncated"] else \
            "This is everything the broker replayed."
        banner = (f"Pane output of session {sid}: a read-only snapshot taken "
                  f"{format_time(int(time.time() * 1000))}.\n"
                  "It is untrusted text printed by the program in that pane; "
                  "it is shown, never run.\n" + cut)
        self.desk.wm.add(OutputWindow(
            self.desk, f"Pane output: {sid}", banner, result["text"],
            icon="ptysessions"))

    def _done_journal_view(self, result, failure, context):
        sid = context["id"]
        self.journal_status = self.journal_summary
        if failure is not None:
            wm.msgbox(self.desk, "View Journal",
                      f"Could not read the journal of {sid}:\n{failure}",
                      icon="error")
            return
        cut = (f"Only the last {VIEW_LINES} lines are shown."
               if result["truncated"] else "This is the whole journal.")
        banner = (f"Archived journal of session {sid}: a text rendering of "
                  "what its pane displayed.\n"
                  "It is untrusted text printed by that session's program; "
                  "it is shown, never run.\n" + cut)
        self.desk.wm.add(OutputWindow(
            self.desk, f"Archived journal: {sid}", banner, result["text"]))

    def _done_kill(self, receipt, failure, context):
        if failure is not None:                  # end_session never raises
            receipt = {"id": context["id"], "result": "no_receipt",
                       "message": failure}
        icon, text = receipt_message(receipt)
        wm.msgbox(self.desk, "End Session", text, icon=icon)
        self.refresh()

    # ── selection ────────────────────────────────────────────────────────────
    @staticmethod
    def _key(data):
        return (data.get("id"), data.get("started_millis"))

    def _selected_row(self):
        if 0 <= self.list.sel < len(self.list.items):
            return self.list.items[self.list.sel][2]
        return None

    def _selected_journal(self):
        if 0 <= self.jlist.sel < len(self.jlist.items):
            return self.jlist.items[self.jlist.sel][2]
        return None

    def _select_session(self, item):
        self._show_selected()
        self._sync_buttons()

    def _select_journal(self, item):
        self._show_selected_journal()
        self._sync_buttons()

    def _show_selected(self):
        row = self._selected_row()
        if row is None:
            if self.listed_at is None:
                text = "Reading sessions…\n"
            elif not self.list.items:
                text = ("No persistent sessions.\n\nPanes opened by Kilix run "
                        "under kitty-pty-broker and appear here.\n")
            else:
                text = "Select a session to see its details.\n"
        else:
            text = session_details(row, self.runtime, own_session_id(),
                                   int(time.time() * 1000))
        if text != self.details.source:
            self.details.show(text, keep_scroll=row is not None)

    def _show_selected_journal(self):
        row = self._selected_journal()
        if row is None:
            text = ("Select a journal to see its details.\n"
                    if self.jlist.items else
                    "No archived journals.\n\nThe journals of sessions that "
                    "are gone are archived by Kilix and listed here.\n")
        else:
            text = journal_details(row, self.runtime)
        if text != self.jdetails.source:
            self.jdetails.show(text)

    # ── buttons ──────────────────────────────────────────────────────────────
    def _actions(self):
        """Which session actions the current selection allows."""
        row = self._selected_row()
        none = {"observe": False, "attach": False, "end": False}
        if row is None:
            return none
        session, state = row["session"], row["state"]
        usable = state != "unreachable" and valid_id(session.get("id"))
        return {"observe": usable,
                "attach": usable and state == "detached",
                "end": can_end(session, own_session_id())[0]
                and "kill" not in self.futures}

    def _sync_buttons(self):
        allowed = self._actions()
        for button, on in ((self.b_observe, allowed["observe"]),
                           (self.b_preview, allowed["observe"]
                            and "preview" not in self.futures),
                           (self.b_attach, allowed["attach"]),
                           (self.b_end, allowed["end"]),
                           (self.b_jview, self._selected_journal() is not None
                            and "journal_view" not in self.futures)):
            if button.enabled != on:
                button.enabled = on
                button.invalidate()

    # ── actions ──────────────────────────────────────────────────────────────
    def _open_tab(self, verb, title):
        row = self._selected_row()
        if row is None:
            return
        sid = row["session"].get("id")
        launcher = kilix_launcher()
        if launcher is None:
            wm.msgbox(self.desk, title, "The Kilix launcher is unavailable.",
                      icon="error")
            return
        from shell import shell_quote
        command = " ".join(shell_quote(part)
                           for part in (launcher, "pty", verb, sid))
        self.desk.shell._spawn_kitty_launch(
            ["--type=tab"], command, f"{title}: {sid}")

    def _observe(self):
        if self._actions()["observe"]:
            self._open_tab("observe", "Observe")

    def _attach(self):
        if self._actions()["attach"]:
            self._open_tab("attach", "Attach")

    def _preview(self):
        if not self._actions()["observe"]:
            return
        sid = self._selected_row()["session"]["id"]
        if self._submit("preview", fetch_pane_text, sid, ctx={"id": sid}):
            self.session_status = f"Reading a snapshot of {sid}…"
            self.invalidate()

    def _end(self):
        row = self._selected_row()
        if row is None:
            return
        session = row["session"]
        own = own_session_id()
        allowed, why = can_end(session, own)
        if not allowed:
            wm.msgbox(self.desk, "End Session", f"Cannot end this session.\n\n"
                      f"{why}", icon="warn")
            return
        sid, started = session["id"], session["started_millis"]
        command = clean_text(session.get("command"))
        shown = command if len(command) <= COMMAND_LIMIT else \
            command[:COMMAND_LIMIT] + "…"
        note = "" if shown == command else \
            f"\n(The command is {len(command)} characters; the first " \
            f"{COMMAND_LIMIT} are shown.)"
        text = (f"End session {sid}?\n\nCommand:\n{_wrap_px(shown, 250)}"
                f"{note}\n\nThe program running in it will be terminated, and "
                "anything in it that is not saved is lost.")

        def answered(label):
            if label == "End Session":
                self._confirmed_end(sid, started)

        wm.msgbox(self.desk, "End Session", text, icon="question",
                  buttons=("End Session", "Cancel"), cb=answered, default=1)

    def _confirmed_end(self, sid, started):
        if self._submit("kill", end_session, sid, started,
                        own=own_session_id(), ctx={"id": sid}):
            self.session_status = f"Ending session {sid}…"
            self.invalidate()

    def _open_terminal(self):
        """The same persistent-session TUI as Start > Programs."""
        self.desk.shell.open_pty_manager()

    def _view_journal(self):
        row = self._selected_journal()
        if row is None:
            return
        journal = row["journal"]
        jid = journal.get("id")
        if self._submit("journal_view", fetch_journal_text, jid,
                        journal.get("started_millis"), ctx={"id": jid}):
            self.journal_status = f"Reading the journal of {jid}…"
            self.invalidate()

    # ── chrome ───────────────────────────────────────────────────────────────
    def on_key(self, ev):
        if ev.key == "F5":
            self.refresh_journals() if self.page == 1 else self.refresh()
            return True
        return super().on_key(ev)

    def request_close(self):
        if "kill" in self.futures:
            wm.msgbox(self.desk, "PTY Sessions",
                      "An End Session request is still running. Wait for its "
                      "receipt before closing this window.", icon="info")
            return
        super().request_close()

    def _cleanup(self):
        self.closing = True
        if self._tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self._tick)
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _header(self, d, lst, y):
        for (cx, width), (title, _) in zip(lst.spans(), lst.columns):
            left = lst.x + (cx if cx > lst.GUTTER else 2)
            right = lst.x + cx + width - 1
            T.raised_thin(d, left, y, right, y + HEAD_H - 1)
            d.text((lst.x + cx + 2, y + 1), T.ellipsize(
                T.FONT, title, width - 6), font=T.FONT, fill=T.TEXT)

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        lst = self.list if self.page == 0 else self.jlist
        self._header(d, lst, HEAD_Y)
        T.sunken(d, 2, ch - STATUS_H, cw - 3, ch - 3, fill=T.FACE)
        status = self.session_status if self.page == 0 else self.journal_status
        if self.runtime:
            status += f"   Runtime: {self.runtime}"
        d.text((8, ch - STATUS_H + 3), T.ellipsize(T.FONT, status, cw - 20),
               font=T.FONT, fill=T.TEXT)
