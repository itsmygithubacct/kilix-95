"""Programs ▸ Local Models (llama.cpp) runs `kilix llama`, held, in a tab.

Always through the Kilix launcher: `kilix llama` installs the kilix-llm this
Kilix pins on first use, and kilix-llm builds llama.cpp on its first chat, so
the entry must not look for an installed kilix-llm first. A kilix-llm on PATH
could be any build; the launcher's is the pinned one. Right-click reaches
status, the updater and rollback, and those tabs hold so their one-shot answer
stays readable.
"""
import os

import harness as H
import icons
import shell


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


def _labels(items):
    return [item.label for item in items if item.label != "-"]


d = H.make_desk()
d.taskbar.open_start_menu()
programs = _find(d.menus.stack[0].items, "Programs")
assert programs is not None and programs.submenu
entry = _find(programs.submenu, "Local Models (llama.cpp)")
assert entry is not None, _labels(programs.submenu)
assert entry.icon in icons.ICONS, entry.icon
assert _labels(entry.context) == [
    "Chat", "Status", "Update llama.cpp", "Roll Back Last Update",
    "Install and Build Now"], _labels(entry.context)

opened = []
d.shell._tab = lambda argv, title, cwd=None, env=None, hold=False: opened.append(
    (list(argv), title, hold))
saved = shell.KILIX_HOME
fake_home = os.path.join(os.environ.get("TMPDIR", "/tmp"), "kilix-home-llama-test")
os.makedirs(fake_home, exist_ok=True)
launcher = os.path.join(fake_home, "kilix")
with open(launcher, "w") as handle:
    handle.write("#!/bin/sh\n")
os.chmod(launcher, 0o755)
try:
    shell.KILIX_HOME = fake_home
    entry.action()
    for item in entry.context:
        item.action()
finally:
    shell.KILIX_HOME = saved
verbs = [argv[2] for argv, _, _ in opened]
assert verbs == ["chat", "chat", "status", "update", "rollback", "install"], opened
for argv, title, hold in opened:
    assert argv[:2] == [launcher, "llama"], argv
    assert hold is True, (argv, hold)
    assert title, argv

# No launcher: words, not a dead tab.
messages = []
saved_msgbox = shell.wm.msgbox
shell.wm.msgbox = lambda *args, **kwargs: messages.append(args)
try:
    shell.KILIX_HOME = os.path.join(fake_home, "missing")
    opened.clear()
    assert d.shell.open_kilix_llama("status") is False
    assert not opened and messages, (opened, messages)
finally:
    shell.KILIX_HOME = saved
    shell.wm.msgbox = saved_msgbox

try:
    d.shell.open_kilix_llama("rm -rf")
except ValueError:
    pass
else:
    raise AssertionError("an unknown verb was accepted")

# _tab passes --hold through to kitten launch only when asked.
launched = []
d.shell._kitten = lambda: "/usr/bin/kitten"
d.shell._resolve_program = lambda program: program
d.shell._popen = lambda argv: launched.append(argv) or True
os.environ.setdefault("KITTY_LISTEN_ON", "unix:/nonexistent")
d.shell._kitten_remote = lambda kitten, verb: [kitten, "@", verb]
H_tab = type(d.shell)._tab
H_tab(d.shell, ["/bin/true"], "t", hold=True)
H_tab(d.shell, ["/bin/true"], "t")
assert "--hold" in launched[0] and "--hold" not in launched[1], launched

print("ok")
