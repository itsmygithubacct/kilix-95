"""Concurrent cell saves replace complete files and never remove another temp."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import tempfile
from unittest.mock import patch

import harness as H  # noqa: F401
import neuronte_face as N

with tempfile.TemporaryDirectory() as temporary:
    target = Path(temporary) / 'cells.bin'
    collision = Path(str(target) + '.%d.tmp' % os.getpid())
    collision.write_bytes(b'another writer')
    payloads = [bytes([i]) * 100000 for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda data: N._write_private(str(target), data), payloads))
    assert target.read_bytes() in payloads
    assert collision.read_bytes() == b'another writer'
    before = target.read_bytes()
    with patch.object(N.os, 'replace', side_effect=OSError('full cache')):
        assert not N._write_private(str(target), b'new')
    assert target.read_bytes() == before
    assert sorted(p.name for p in target.parent.iterdir()) == sorted([target.name, collision.name])
    assert target.stat().st_mode & 0o777 == 0o600
print('ok')
