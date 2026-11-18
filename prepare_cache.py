"""Prepare the current user's desktop caches with the launcher's interpreter.

`python3 main.py --prepare-cache`, run as the desktop user after an install or
an update, writes what a first start would otherwise build: the Kilix 95 and
Kilix SDK bytecode (bytecode.py: this checkout, the SDK and the packages it
pins, whole, so applications open without compiling either) and the two
start-up Neuronte letter caches. System modules are not compiled: main.py
loads them from the bytecode the distribution ships. Bytecode whose source is
gone is pruned. Exit status 0 when both are written, 1 when a file could not
be compiled, 2 when run as root.
"""
import os
import sys
import threading


def prepare(root, kilix_home, prefix, launch_modules):
    if os.geteuid() == 0:
        print("kilix-95: refusing to prepare caches as root; run it as the "
              "desktop user", file=sys.stderr)
        return 2
    # Normal startup fills the two UI faces in the background. Finish them
    # first: nothing else may run while bytecode.py imports what it needs.
    for thread in threading.enumerate():
        if thread.name == 'neuronte-letters':
            thread.join()
    import bytecode
    status = bytecode.compile_desktop(prefix, root, kilix_home, launch_modules)
    # ... and save them, so installation prepares those files for the first
    # desktop too.
    import neuronte_face
    neuronte_face.save_letters()
    print('Kilix 95 caches prepared' if status == 0 else
          'Kilix 95 caches prepared, except the bytecode named above')
    return status
