"""Install-time preparation works without a display or native state library."""
from pathlib import Path
import os
import subprocess
import sys

import harness as H  # noqa: F401
import storage

root = Path(__file__).resolve().parents[1]
env = dict(os.environ, KILIX_STATE_LIBRARY='/missing/libkilix-state.so')
env.pop('PYTHONDONTWRITEBYTECODE', None)
prefix = Path(storage.cache_dir('pycache'))


def run(*args, native=False):
    runtime = dict(env, KILIX_STATE_LIBRARY=os.environ['KILIX_STATE_LIBRARY']) if native else env
    result = subprocess.run([sys.executable, str(root / 'main.py'), *args],
                            env=runtime, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


run('--prepare-cache')
files = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in prefix.rglob('*.pyc')}
assert any(p.name.startswith('theme.') for p in files)
assert any(p.name.startswith('wordpad.') for p in files)
# System modules keep the distribution's bytecode (test_system_bytecode.py).
assert not any(p.name.startswith('ImageDraw.') for p in files)
assert all(str(p).startswith(str(prefix) + os.sep) for p in files)
# Preparing twice and launching again consume the existing bytecode. A source
# update is invalidated by Python's normal mtime/size checks on the next prepare.
run('--prepare-cache')
run('--version')
run('--screenshot', str(prefix.parent / 'first-frame.png'), native=True)
assert files == {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in prefix.rglob('*.pyc')}
print('ok')
