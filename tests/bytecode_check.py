"""Shared helpers for the bytecode tests: start main.py the way the Kilix launcher does.

The launcher runs `PYTHONPYCACHEPREFIX=<Kilix 95 cache>/pycache python3 main.py`
in a terminal. start() does the same in a pseudo-terminal with an empty or
pre-filled cache, through a short driver. The driver records which files the
interpreter had loaded before main.py ran. It turns off the default-voice
install, which would start `kilix tts --install` in a session of its own.
Then it runs main.py's code unchanged, or with its _SYSTEM_MODULES list
emptied. The start is stopped a few seconds after its first frame; every
system module start-up uses is imported before that frame.

Not a test itself (run.py only runs test_*.py).
"""
import ast
import fcntl
import importlib.util
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KILIX_HOME = os.path.abspath(os.environ["KILIX_HOME"])
TREES = tuple(sorted({ROOT, os.path.realpath(ROOT), KILIX_HOME,
                      os.path.realpath(KILIX_HOME)}))
TAG = "." + sys.implementation.cache_tag + ".pyc"

# Uses only sys and os, which the interpreter has loaded before any script runs,
# so the launch set it records is the interpreter's own and not the driver's.
DRIVER = r'''
import os, sys
report, main_path, empty = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
files = [m.__file__ for m in list(sys.modules.values())
         if isinstance(getattr(m, "__file__", None), str)]
fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, "\n".join(files).encode())
os.close(fd)
with open(main_path, encoding="utf-8") as fh:
    source = fh.read()
if empty:
    for name in ("_SYSTEM_MODULES", "_FONT_MODULES"):
        start = source.index(name + " = (")
        multiline = source.startswith(name + " = (\n", start)
        end = source.index("\n)\n" if multiline else ")\n", start) + (2 if multiline else 1)
        source = source[:start] + name + " = ()" + source[end:]
sys.argv = [main_path]
sys.path[0] = os.path.dirname(main_path)
scope = {"__name__": "kilix95_bytecode_test", "__file__": main_path}
exec(compile(source, main_path, "exec"), scope)
import system_voice
system_voice.Controller.install_default_voice = lambda self: False
scope["main"]()
'''

# The start-up benchmark's interactive environment: no sound, no
# offers, no screen saver, the shortest splash.
QUIET = {
    "KILIX_NO_SOUND": "1", "KILIX_MODEL_WIZARD_OFFER": "0",
    "KILIX_SYSTEM_VOICE_OFFER": "0", "KILIX_SAVER_IDLE": "86400",
    "KILIX_STARTUP_SCREEN_SECONDS": "1.0", "TERM": "xterm-kitty",
}
UNSET = ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "DISPLAY",
         "XAUTHORITY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "TMUX",
         "PLEB_DESKTOP_DISPLAY", "PLEB_DESKTOP_XAUTHORITY", "SOURCE_DATE_EPOCH")


def scratch(tag):
    return tempfile.mkdtemp(prefix=f"kilix95-{tag}-")


def env_for(cache_home, launcher=True, extra=None):
    """Run.py's sandbox env with this cache, as the launcher (or an installer) sets it."""
    env = {k: v for k, v in os.environ.items() if k not in UNSET}
    env.update(QUIET)
    env["KILIX95_CACHE_HOME"] = cache_home
    env["KILIX_HOST_CLIP"] = "0"
    if launcher:
        env["PYTHONPYCACHEPREFIX"] = os.path.join(cache_home, "pycache")
    env.update(extra or {})
    return env


def start(env, workdir, empty_list=False, settle=2.0, first_timeout=40):
    """Start main.py in a pty; stop it `settle` s after its first frame.

    Returns the files the interpreter had loaded before main.py ran."""
    driver = os.path.join(workdir, "driver.py")
    report = os.path.join(workdir, "launch.txt")
    with open(driver, "w") as fh:
        fh.write(DRIVER)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 160, 960, 1280))
    proc = subprocess.Popen(
        [sys.executable, driver, report, os.path.join(ROOT, "main.py"),
         "1" if empty_list else "0"],
        env=env, cwd=workdir, stdin=slave, stdout=slave, stderr=slave,
        start_new_session=True)
    os.close(slave)
    out = b""
    first = None
    deadline = time.monotonic() + first_timeout
    try:
        while proc.poll() is None:
            now = time.monotonic()
            if first is None and now > deadline:
                break
            if first is not None and now > first + settle:
                break
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                out += chunk
                if first is None and b"\x1b_G" in out:
                    first = time.monotonic()
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            except ProcessLookupError:
                pass
        os.close(master)
    tail = out[-3000:].decode("utf-8", "replace")
    assert first is not None, "no desktop frame; exit %r, output:\n%s" % (
        proc.returncode, tail)
    with open(report) as fh:
        return [os.path.abspath(f) for f in fh.read().split("\n") if f]


def prefix_sources(prefix):
    """The source file each .pyc under prefix stands for."""
    out = []
    for directory, _dirs, files in os.walk(prefix):
        for name in files:
            if not name.endswith(TAG):
                continue
            source_dir = "/" + os.path.relpath(directory, prefix)
            out.append(os.path.normpath(
                os.path.join(source_dir, name[:-len(TAG)] + ".py")))
    return sorted(out)


def cached_path(prefix, source):
    base = os.path.basename(source)[:-3]
    return os.path.join(prefix, os.path.dirname(source).lstrip("/"), base + TAG)


def in_trees(path):
    return any(os.path.commonpath((path, t)) == t for t in TREES)


def tree_pycache():
    found = set()
    for root in (ROOT, KILIX_HOME):
        for directory, dirs, _files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (".git", "src")]
            if "__pycache__" in dirs:
                found.add(os.path.join(directory, "__pycache__"))
    return found


def _tuple(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                [t.id for t in node.targets if isinstance(t, ast.Name)] == [name]:
            return [elt.value for elt in node.value.elts]
    raise AssertionError("main.py has no " + name)


def system_list():
    """main.py's _SYSTEM_MODULES, plus the _FONT_MODULES this Pillow's
    FreeTypeFont() imports (main.py's own rule), read from the source."""
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = _tuple(tree, "_SYSTEM_MODULES")
    try:
        from PIL import ImageFont
        used = ImageFont.FreeTypeFont.__init__.__code__.co_names
    except Exception:
        used = ()
    return names + [n for n in _tuple(tree, "_FONT_MODULES") if n in used]


def module_source(name):
    """The .py file of a module on this Python, or None when it has none."""
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    origin = getattr(spec, "origin", None)
    if spec is None or not spec.has_location or not isinstance(origin, str) \
            or not origin.endswith(".py"):
        return None
    return os.path.abspath(origin)


def remove(path):
    shutil.rmtree(path, ignore_errors=True)
