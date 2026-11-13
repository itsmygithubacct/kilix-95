"""Placement data is read without executing training code, even on a first run."""
import json
from pathlib import Path
import tempfile

import harness as H  # noqa: F401
import neuronte_face as N

original = N._ROOT
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / 'font').mkdir()
    (root / 'train').mkdir()
    (root / 'train/glyphs.py').write_text('raise RuntimeError("must not execute")\n')
    path = root / 'font/ui-tops.json'
    tops = {str(em): em // 2 for em in range(1, 129) if em != 44}
    good = {'schema': 'neuronte.ui-tops/v1', 'tops': tops}
    try:
        N._ROOT = str(root)
        N._tops = None
        assert N._ui_tops() == {}   # missing metadata needs header placement
        path.write_text(json.dumps(good))
        N._tops = None
        assert N._ui_tops() == {int(em): row for em, row in tops.items()}
        for bad in ('', '{', '[]', 'null', ' ' * 65537,
                    json.dumps(dict(good, schema='unknown')),
                    json.dumps(dict(good, tops={})),
                    *(json.dumps(dict(good, tops=dict(tops, **{'11': value})))
                      for value in (-1, 99, True, 1.5, '6', None))):
            path.write_text(bad)
            N._tops = None
            assert N._ui_tops() == {}, bad[:80]
    finally:
        N._ROOT, N._tops = original, None
print('ok')
