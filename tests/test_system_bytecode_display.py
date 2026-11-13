"""With a host display, start-up's system modules still come from Debian's bytecode.

Desk._run connects to the host X display for the shared clipboard. Connecting
imports python-xlib's connection and authority modules, plus a module for
each X extension the server has. main.py imports those before it sets the
bytecode prefix when the same condition holds (KILIX_HOST_CLIP not 0 and
DISPLAY set). Against a private Xvfb, an interactive start must leave in the
prefix only Kilix 95 and Kilix SDK bytecode and the modules loaded before
main.py ran (see test_system_bytecode.py). Skipped when Xvfb is not installed.
"""
import os
import shutil
import subprocess

import bytecode_check as B

xvfb = shutil.which("Xvfb")
if not xvfb:
    print("skip: Xvfb is not installed")
    raise SystemExit(0)

sandbox = B.scratch("system-bytecode-display")
server = None
try:
    before = B.tree_pycache()
    read_fd, write_fd = os.pipe()
    server = subprocess.Popen(
        [xvfb, "-displayfd", str(write_fd), "-nolisten", "tcp",
         "-screen", "0", "1280x800x24"],
        pass_fds=(write_fd,), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    os.close(write_fd)
    with os.fdopen(read_fd) as fh:
        number = fh.readline().strip()
    assert number.isdigit(), "Xvfb did not report a display"
    cache = os.path.join(sandbox, "cache")
    work = os.path.join(sandbox, "run")
    os.makedirs(work)
    env = B.env_for(cache, extra={"DISPLAY": ":" + number,
                                  "KILIX_HOST_CLIP": "1"})
    launch = set(B.start(env, work))
    sources = B.prefix_sources(os.path.join(cache, "pycache"))
    assert any(s.endswith("/clipboard.py") and B.in_trees(s) for s in sources), \
        "the start did not open the host display: %s" % sources
    stray = [s for s in sources if not B.in_trees(s) and s not in launch]
    assert not stray, (
        "with a display, start-up compiled these system modules into the "
        "Kilix 95 prefix; import them before the prefix in main.py:\n  "
        + "\n  ".join(stray))
    assert B.tree_pycache() == before, sorted(B.tree_pycache() - before)
finally:
    if server is not None:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    B.remove(sandbox)

print("ok")
