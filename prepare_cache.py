"""Prepare the current user's desktop caches with the launcher's interpreter."""
import compileall
from pathlib import Path
import sys
import threading


def prepare(root, kilix_home):
    # These imports normally happen during the first paint or sound setup.
    # Importing them here starts no workers and opens no audio device.
    from concurrent.futures import ThreadPoolExecutor  # noqa: F401
    import wave  # noqa: F401
    from PIL import Image
    Image.preinit()
    # Imported dependencies include system modules whose Debian bytecode is
    # bypassed by sys.pycache_prefix. Applications and SDK modules loaded only
    # on demand are compiled too, without importing or launching them.
    paths = {Path(module.__file__) for module in tuple(sys.modules.values())
             if (getattr(module, '__file__', None) or '').endswith('.py')}
    root = Path(root)
    paths.update(root.glob('*.py'))
    paths.update((root / 'apps').rglob('*.py'))
    paths.update((Path(kilix_home) / 'config/kilix_sdk').rglob('*.py'))
    if not sys.pycache_prefix:
        raise RuntimeError('desktop bytecode cache is not configured')
    failed = [str(path) for path in sorted(paths)
              if not compileall.compile_file(str(path), quiet=1)]
    if failed:
        raise RuntimeError('could not prepare bytecode: ' + ', '.join(failed))
    # Normal startup fills the two UI faces in the background. Finish and save
    # them here so installation prepares those files for the first desktop too.
    for thread in threading.enumerate():
        if thread.name == 'neuronte-letters':
            thread.join()
    import neuronte_face
    neuronte_face.save_letters()
    print('Kilix 95 caches prepared')
