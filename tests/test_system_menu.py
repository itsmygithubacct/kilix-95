"""Start ▸ System offers only the update/maintenance actions actually present.

Drives shell.system_menu_items() with a faked filesystem (os.path.exists/isdir/
listdir/access monkeypatched) so each detection branch is exercised without
touching the real machine.
"""
import os

import harness as H
import shell as shell_mod


def _labels(items):
    return [it.label for it in items if it.label != "-"]


DESK = H.make_desk()          # build BEFORE patching os (Shell.__init__ mkdir)


def run_case(present_files, present_dirs, dir_listing, expect):
    """present_files: set of paths os.path.exists() should return True for.
       present_dirs:  set of paths os.path.isdir() should return True for.
       dir_listing:   {dir: [names]} for os.listdir(); those names are X_OK."""
    real_exists, real_isdir = os.path.exists, os.path.isdir
    real_listdir, real_access = os.listdir, os.access
    execable = {os.path.join(d, n) for d, ns in dir_listing.items() for n in ns}

    os.path.exists = lambda p: p in present_files
    os.path.isdir = lambda p: p in present_dirs
    os.listdir = lambda p: dir_listing.get(p, [])
    os.access = lambda p, m: p in execable
    try:
        items = DESK.shell.system_menu_items()   # only the call is patched
    finally:
        os.path.exists, os.path.isdir = real_exists, real_isdir
        os.listdir, os.access = real_listdir, real_access
    assert _labels(items) == expect, (_labels(items), expect)
    return items


KH = shell_mod.KILIX_HOME
HOME = os.path.expanduser("~")

# nothing installed → empty menu (the caller then omits the whole entry)
run_case(set(), set(), {}, [])

# a bare kilix git checkout (no pleb) → only "Update kilix"
run_case(
    present_files={os.path.join(KH, "kilix")},
    present_dirs={os.path.join(KH, ".git")},
    dir_listing={},
    expect=["Update kilix"])

# pleb present but not a kilix checkout → only "Update Pleb"
run_case(
    present_files={os.path.join(HOME, "pleb", "bin", "pleb")},
    present_dirs=set(),
    dir_listing={},
    expect=["Update Pleb (kilix + session)"])

# a full Plebian-OS box: kilix + pleb + the installed stack scripts + an extra
# maintenance script under ~/pleb/scripts
items = run_case(
    present_files={
        os.path.join(KH, "kilix"),
        os.path.join(HOME, "pleb", "bin", "pleb"),
        "/usr/local/bin/plebian-os-update",
        "/usr/local/sbin/plebian-os-install-deps",
    },
    present_dirs={
        os.path.join(KH, ".git"),
        os.path.join(HOME, "pleb", "scripts"),
    },
    dir_listing={os.path.join(HOME, "pleb", "scripts"):
                 ["install-go.sh", "notes.txt"]},
    expect=["Update kilix", "Update Pleb (kilix + session)",
            "Update Plebian-OS (kilix + pleb)", "Reinstall dependencies",
            "Scripts"])
# the Scripts submenu carries only the executable *.sh (not notes.txt)
scripts = [it for it in items if it.label == "Scripts"][0]
assert _labels(scripts.submenu) == ["install-go.sh"], _labels(scripts.submenu)
# every actionable item is clickable
assert all(callable(it.action) for it in items if it.submenu is None
           and it.label != "-")

# Plebian-OS 0.2.3 with the SSH server helper: one submenu, three launchers
# running the same helper (sudo for the two that change anything).
SSH = "/usr/local/sbin/plebian-os-ssh-server"
items = run_case(
    present_files={"/usr/local/sbin/plebian-os-install-deps", SSH},
    present_dirs=set(),
    dir_listing={},
    expect=["Reinstall dependencies", "Remote login (SSH)"])
ssh_menu = [it for it in items if it.label == "Remote login (SSH)"][0]
assert _labels(ssh_menu.submenu) == ["Turn SSH on", "Turn SSH off",
                                     "Show SSH status"], _labels(ssh_menu.submenu)
ran = []
DESK.shell.run_maintenance = lambda cmd, title: ran.append((cmd, title))
try:
    for it in ssh_menu.submenu:
        it.action()
finally:
    del DESK.shell.run_maintenance
assert ran == [(shell_mod.ssh_enable_command(SSH), "Turn SSH on"),
               (f'sudo "{SSH}" disable', "Turn SSH off"),
               (f'"{SSH}" status', "Show SSH status")], ran

# "Turn SSH on" warns and asks [y/N] in its tab before sudo runs anything, so
# a machine whose sudo needs no password still never opens SSH from a click.
import subprocess
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    log = os.path.join(tmp, "calls")
    stub_helper = os.path.join(tmp, "plebian os ssh-server")  # a space: quoting holds
    with open(stub_helper, "w") as f:
        f.write(f'#!/bin/sh\necho "helper $*" >> "{log}"\necho "SSH server: OFF"\n')
    os.chmod(stub_helper, 0o755)
    with open(os.path.join(tmp, "sudo"), "w") as f:
        f.write(f'#!/bin/sh\necho "sudo $*" >> "{log}"\n')
    os.chmod(os.path.join(tmp, "sudo"), 0o755)
    command = shell_mod.ssh_enable_command(stub_helper)
    env = dict(os.environ, PATH=tmp + ":/usr/bin:/bin")
    for reply, expect in (("\n", [f"helper status"]), ("", ["helper status"]),
                          ("n\n", ["helper status"]), ("yep\n", ["helper status"]),
                          ("y\n", [f"sudo {stub_helper} enable"]),
                          (" YES \n", [f"sudo {stub_helper} enable"])):
        if os.path.exists(log):
            os.unlink(log)
        out = subprocess.run(["bash", "-c", command], input=reply, env=env,
                             capture_output=True, text=True, timeout=10)
        assert out.returncode == 0, (reply, out)
        assert "Every account on this computer that has a password" in out.stdout, out.stdout
        assert "Turn SSH on now? [y/N]" in out.stdout, out.stdout
        with open(log) as f:
            assert f.read().splitlines() == expect, (reply, expect)
        if not expect[0].startswith("sudo"):
            assert "SSH was not changed." in out.stdout, out.stdout
# without the helper (an older OS layer, or a plain checkout) there is no entry
run_case({SSH}, set(), {}, ["Remote login (SSH)"])
run_case({"/usr/local/sbin/plebian-os-install-deps"}, set(), {},
         ["Reinstall dependencies"])

print("test_system_menu OK")
