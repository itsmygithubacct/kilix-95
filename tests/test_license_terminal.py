"""The embedded terminal is a real PTY; Yes/No input stays on the desktop."""
import os
import sys
import time
import harness as H
from apps.licenseterminal import open_window


def until(predicate, window, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        window.pump()
        window.tick(0)
        time.sleep(.01)
    assert predicate(), window.output


with H.desktop_dir():
    desk = H.make_desk()
    script = "import sys; print('TTY', sys.stdin.isatty(), sys.stdout.isatty(), flush=True); a=input('Accept Apache 2.0 for model1, model2? [y/N] '); print('ANSWER='+a, flush=True)"
    window = open_window(desk, [sys.executable, '-c', script])
    until(lambda: window.yes.enabled, window)
    assert 'TTY True True' in window.output
    assert window in desk.wm.windows
    preview = os.environ.get('LICENSE_PREVIEW')
    if preview: window.render().save(preview)
    window.yes.cb()
    assert not window.yes.enabled
    until(lambda: window.finished, window)
    assert 'ANSWER=y' in window.output and window.process.returncode == 0
    window.close()
    assert window.master is None and window.tick not in desk.tick_hooks

    window = open_window(desk, [sys.executable, '-c',
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"])
    until(lambda: 'ready' in window.output, window)
    window.close()
    assert window.process.poll() is not None
    assert window.master is None

print('embedded licence terminal: OK')
