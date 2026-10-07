"""PTY Sessions' kilix pty client: contract parsing, bounds, receipts.

Runs the app's backend against a fake `kilix pty` executable that prints the
documents of the kilix.pty/v1 contract. No broker, no Kilix store, no desktop.
"""
import harness as H  # noqa: F401  (puts the desktop dir on sys.path)
import pty_fake as F
from apps import ptysessions as P


def raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except P.PtyError as error:
        return str(error)
    raise AssertionError("expected PtyError")


fake = F.FakeKilix(F.standard_responses())
L = fake.path

# ── list: sessions and unreachable are separate, nothing is dropped ─────────
data = P.load_sessions(L)
assert data["runtime"] == F.RUNTIME
assert [s["id"] for s in data["sessions"]] == [
    F.DETACHED["id"], F.ATTACHED["id"]]
assert [s["id"] for s in data["unreachable"]] == [F.UNREACHABLE["id"]]
assert data["unreachable"][0]["reachable"] is False
assert fake.calls() == [["pty", "list", "--json"]], fake.calls()

# unknown fields are ignored, not fatal (the contract may grow within v1)
fake.set([F.response(["pty", "list"], F.doc(F.LIST, future_field=[1, 2]))])
assert len(P.load_sessions(L)["sessions"]) == 2

# a different schema, non-JSON, an array, a missing list and a failed exit
# are all errors that say so — never an empty listing
fake.set([F.response(["pty", "list"], F.doc(F.LIST, schema="kilix.pty/v2"))])
assert "schema" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], "not json at all")])
assert "not JSON" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], "[]")])
assert raises(P.load_sessions, L)
bad = F.doc(F.LIST)
del bad["unreachable"]
fake.set([F.response(["pty", "list"], bad)])
assert "malformed" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], None, 1,
                     "kilix pty: broker runtime is gone\n")])
assert raises(P.load_sessions, L) == "kilix pty: broker runtime is gone"
fake.set([F.response(["pty", "list"], F.LIST, 1)])
assert "exit status 1" in raises(P.load_sessions, L)

# a call that does not return within its bound is an error, not a hang
fake.set([F.response(["pty", "list"], F.LIST, sleep=5)])
assert "did not answer" in raises(P.run_pty, ["list", "--json"], L, 1)

# a missing launcher is explained
try:
    P.run_pty(["list"], "/nonexistent/kilix")
except P.PtyError as error:
    assert "Could not start" in str(error), error
else:
    raise AssertionError("a missing launcher was accepted")

# ── rows and states ─────────────────────────────────────────────────────────
assert P.session_state(F.DETACHED) == "detached"
assert P.session_state(F.ATTACHED) == "attached"
assert P.session_state(F.UNREACHABLE) == "unreachable"
now = F.DETACHED["started_millis"] + 5 * 60 * 1000 + 7
assert P.format_age(F.DETACHED["started_millis"], now) == "5m"
assert P.format_age(1000, 1000 + 7 * 3600 * 1000 + 120000) == "7h 02m"
assert P.format_age(1000, 1000 + 3 * 86400 * 1000) == "3d 0h"
assert P.format_age(None, now) == "?"
icon, label, row = P.session_row(F.DETACHED, now)
assert row["cells"] == ("3fa9c2d41b7e6a05", "detached", "5m", "80x24",
                        'sh -c echo "build ok"; sleep 300',
                        "/srv/work/build"), row["cells"]
assert "detached" in label and "/srv/work/build" in label
icon, label, row = P.session_row(F.UNREACHABLE, now)
assert icon == "warn" and row["state"] == "unreachable"
assert "UNREACHABLE" in label and F.UNREACHABLE["id"] in label
assert row["cells"][1] == "UNREACHABLE" and "timeout" in row["cells"][4]

# ── ids and untrusted text ──────────────────────────────────────────────────
for ok in ("3fa9c2d41b7e6a05", "a.b_c-9", "x" * 64):
    assert P.valid_id(ok), ok
for bad in ("", ".", "..", "x" * 65, "a b", "a/b", "a;b", "$(id)", "é", None,
            "a\n", "-x"[:0]):
    assert not P.valid_id(bad), repr(bad)
assert P.clean_text("a\x1b[31mred\x07\x00") == "a [31mred  "
assert P.clean_text("a\x1b[31m\x9b\u202etxt\u202c\r\nb", multiline=True) \
    == "a?[31m??txt?\nb"
assert "\x1b" not in P.clean_text("\x1b]0;title\x07", multiline=True)

# ── a pane snapshot is bounded and sanitised ────────────────────────────────
fake.set(F.standard_responses())
text = P.fetch_pane_text(F.DETACHED["id"], L)
assert text == {"text": "build ok\ntests: 42 passed\n", "truncated": False,
                "total_bytes": 28}, text
last = [c for c in fake.calls() if c[:2] == ["pty", "observe"]][-1]
assert last == ["pty", "observe", F.DETACHED["id"], "--once", "--lines", "200",
                "--text", "--json"], last
hostile = "\n".join(f"line {i}\x1b[2J\x1b]52;c;ZXZpbA==\x07" for i in range(500))
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text=hostile, truncated=False))])
out = P.fetch_pane_text(F.DETACHED["id"], L)
assert out["truncated"] is True
assert len(out["text"].split("\n")) <= P.VIEW_LINES + 1
assert "\x1b" not in out["text"] and "\x07" not in out["text"]
assert out["text"].splitlines()[-1].startswith("line 499")
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text="x" * (P.VIEW_CHARS * 3)))])
assert len(P.fetch_pane_text(F.DETACHED["id"], L)["text"]) == P.VIEW_CHARS
fake.set([F.response(["pty", "observe"], F.doc(F.OBSERVE, id="ffffffffffffffff"))])
assert "different session" in raises(P.fetch_pane_text, F.DETACHED["id"], L)
fake.set([F.response(["pty", "observe"], F.doc(F.OBSERVE, text=None))])
assert "without text" in raises(P.fetch_pane_text, F.DETACHED["id"], L)
fake.set([F.response(["pty", "observe"], None, 1, "kilix pty: gone\n")])
assert raises(P.fetch_pane_text, F.DETACHED["id"], L) == "kilix pty: gone"
fake.clear()
raises(P.fetch_pane_text, "bad id;", L)
assert fake.calls() == [], "an unusable id reached kilix"

# ── journals ────────────────────────────────────────────────────────────────
fake.set(F.standard_responses())
journals = P.load_journals(L)["journals"]
assert [j["id"] for j in journals] == ["90d1e57a2c4b8f36"]
view = P.fetch_journal_text("90d1e57a2c4b8f36", 1791337517964, L)
assert view["text"] == "old out\n"
assert fake.calls()[-1] == ["pty", "journals", "show",
                            "90d1e57a2c4b8f36.1791337517964", "--text",
                            "--json", "--lines", "200"], fake.calls()[-1]

# ── end_session: exactly the contract's receipts, truthfully ────────────────
sid, started = F.DETACHED["id"], F.DETACHED["started_millis"]
for doc in (F.VERIFIED, F.UNCERTAIN, F.UNCERTAIN_UNSENT, F.REFUSED_OWN,
            F.REFUSED_MISMATCH, F.NOT_FOUND_RECEIPT):
    fake.set([F.kill_response(doc)])
    fake.clear()
    got = P.end_session(sid, started, L)
    assert got["result"] == doc["result"], (doc["result"], got)
    assert fake.calls() == [["pty", "kill", sid, "--yes", "--expect-started",
                             str(started), "--json"]], fake.calls()

# a receipt that lies about its exit status is not believed
fake.set([F.response(["pty", "kill"], F.VERIFIED, 1)])
got = P.end_session(sid, started, L)
assert got["result"] == "no_receipt", got
fake.set([F.response(["pty", "kill"], F.UNCERTAIN, 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
# a receipt for another session, an unknown result, no JSON: no receipt
fake.set([F.response(["pty", "kill"], F.doc(F.VERIFIED, id="ffffffffffffffff"), 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
fake.set([F.response(["pty", "kill"], F.doc(F.VERIFIED, result="gone"), 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
fake.set([F.response(["pty", "kill"], None, 2, "kilix pty: kill needs --yes\n")])
got = P.end_session(sid, started, L)
assert got["result"] == "no_receipt" and "needs --yes" in got["message"], got
# a kill that never returns: no receipt, never success
fake.set([F.response(["pty", "kill"], F.VERIFIED, 0, sleep=5)])
orig = P.KILL_TIMEOUT
P.KILL_TIMEOUT = 1
try:
    got = P.end_session(sid, started, L)
finally:
    P.KILL_TIMEOUT = orig
assert got["result"] == "no_receipt" and "did not answer" in got["message"], got
assert P.receipt_message(got)[0] == "error"

# the desktop's own session is refused locally: kilix is never even called
fake.set([F.kill_response(F.VERIFIED)])
fake.clear()
got = P.end_session(sid, started, L, own=sid)
assert got["result"] == "refused" and got["reason"] == "own_session", got
assert got["request_sent"] is False
assert fake.calls() == [], "an own-session end reached kilix"
# an unnameable session is not sent either
got = P.end_session(sid, None, L)
assert got["result"] == "no_receipt" and fake.calls() == []
got = P.end_session("bad id", started, L)
assert got["result"] == "no_receipt" and fake.calls() == []

# can_end: the one place that decides
assert P.can_end(F.DETACHED) == (True, "")
assert P.can_end(F.ATTACHED)[0] is True          # an attached session may end
assert not P.can_end(F.UNREACHABLE)[0]
# even if a future contract adds a start time to an unreachable entry
assert not P.can_end(F.doc(F.UNREACHABLE, started_millis=1791337517862))[0]
assert not P.can_end(F.DETACHED, own=sid)[0]
assert P.can_end(F.DETACHED, own="ffffffffffffffff")[0]
assert not P.can_end(F.doc(F.DETACHED, started_millis=None))[0]
assert not P.can_end(F.doc(F.DETACHED, id="a b"))[0]

# receipts read truthfully
text = {r: P.receipt_message(F.doc(d, result=d["result"]))
        for r, d in (("verified_absent", F.VERIFIED), ("uncertain", F.UNCERTAIN),
                     ("refused", F.REFUSED_OWN), ("not_found", F.NOT_FOUND_RECEIPT))}
assert text["verified_absent"][0] == "info"
assert "has ended" in text["verified_absent"][1]
assert "verified_absent" in text["verified_absent"][1]
assert text["uncertain"][0] == "warn" and "uncertain" in text["uncertain"][1]
assert "WAS sent" in text["uncertain"][1] and "Refresh" in text["uncertain"][1]
assert "has ended" not in text["uncertain"][1]
unsent = P.receipt_message(F.UNCERTAIN_UNSENT)[1]
assert "status_failed" in unsent and "Nothing was sent" in unsent, unsent
assert "WAS sent" not in unsent and "has ended" not in unsent
assert "Nothing was sent" in P.receipt_message(F.doc(
    F.UNCERTAIN_UNSENT, reason="status_timeout"))[1]
# the real receipts omit started_millis / waited_ms when nothing was polled
for bare in (F.UNCERTAIN_UNSENT, F.REFUSED_OWN, F.NOT_FOUND_RECEIPT):
    assert "started_millis" not in bare and "waited_ms" not in bare, bare
assert "waited_ms" not in F.REFUSED_MISMATCH
assert F.VERIFIED["waited_ms"] and F.VERIFIED["started_millis"]
assert P.receipt_message(F.VERIFIED)[0] == "info"
assert "own_session" in text["refused"][1] and "Nothing was ended" in text["refused"][1]
assert "not_found" in text["not_found"][1]
assert "has ended" not in text["refused"][1] + text["not_found"][1]

print("ok")
