"""Owned launcher group cleanup when a graphical read times out."""
import os
from pathlib import Path
import signal
import tempfile
import time

import harness as H  # noqa: F401
from apps import ptysessions as P

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    marker = root / 'child'
    launcher = root / 'launcher'
    launcher.write_text('#!/usr/bin/env python3\n'
                        'import os, subprocess, time\n'
                        'child = subprocess.Popen(["sleep", "30"])\n'
                        f'open({str(marker)!r}, "w").write(str(child.pid))\n'
                        'try:\n    child.wait()\n'
                        'finally:\n    child.terminate()\n    child.wait()\n')
    launcher.chmod(0o700)
    try:
        P.run_pty(['list', '--json'], str(launcher), timeout=0.4)
        raise AssertionError('expected timeout')
    except P.PtyError as error:
        assert 'did not answer' in str(error)
    pid = int(marker.read_text())
    # A reparented zombie is stopped; it is reaped by the host's init.
    end = time.monotonic() + 2
    while True:
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
        except FileNotFoundError:
            break
        if state == 'Z':
            break
        assert time.monotonic() < end, 'owned child survived timeout'
        time.sleep(0.02)
print('owned launcher timeout cleanup passed')
