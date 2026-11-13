"""`main.py --prepare-cache` prunes bytecode whose source is gone, and nothing else.

Without it the private prefix would grow with every update that moves or
removes a module. It removes a .pyc of any Python version or optimization
level whose source file no longer exists, an interrupted atomic write older
than an hour, and the directories that leaves empty. It keeps a .pyc whose
source exists (of any Python version), a fresh temporary file (a write may be
in progress), a file it does not recognize, and a symlink, which it never
follows. A file it cannot remove is reported without failing the step.
"""
import os
import py_compile
import subprocess
import sys
import time

import bytecode_check as B


def prepare(env):
    return subprocess.run(
        [sys.executable, os.path.join(B.ROOT, "main.py"), "--prepare-cache"],
        env=env, cwd=sandbox, capture_output=True, text=True, timeout=120)


def snapshot(prefix):
    out = {}
    for directory, _dirs, files in os.walk(prefix):
        for name in files:
            path = os.path.join(directory, name)
            st = os.lstat(path)
            out[path] = (st.st_mtime_ns, st.st_size, st.st_ino)
    return out


def plant(path, data=b"stale", age=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    if age:
        then = time.time() - age
        os.utime(path, (then, then))
    return path


sandbox = B.scratch("prune")
try:
    before = B.tree_pycache()
    cache = os.path.join(sandbox, "cache")
    prefix = os.path.join(cache, "pycache")
    installer = B.env_for(cache, launcher=False)
    r = prepare(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 0 pruned" in r.stdout, r.stdout
    settled = snapshot(prefix)
    in_root = os.path.join(prefix, B.ROOT.lstrip("/"))
    theme = B.cached_path(prefix, os.path.join(B.ROOT, "theme.py"))
    assert theme in settled, theme

    # Removed: stale bytecode, an old interrupted write, a really compiled
    # module whose source was then deleted.
    gone = [
        plant(B.cached_path(prefix, os.path.join(B.ROOT, "gone_module.py"))),
        plant(os.path.join(in_root, "gone_other.cpython-39.opt-1.pyc")),
        plant(os.path.join(in_root, "gone_pypy.pypy39.pyc")),
        plant(B.cached_path(prefix, os.path.join(B.ROOT, "gone_pkg", "__init__.py"))),
        plant(B.cached_path(prefix, os.path.join(B.ROOT, "gone_pkg", "sub", "deep.py"))),
        plant(theme + ".12345", age=7200),
    ]
    source = os.path.join(sandbox, "src", "moved.py")
    plant(source, b"VALUE = 1\n")
    compiled = B.cached_path(prefix, source)
    py_compile.compile(source, cfile=compiled, doraise=True)
    os.unlink(source)
    gone.append(compiled)

    # Kept: another Python's bytecode for a source that exists, a write that
    # may be in progress, files this step does not recognize, symlinks.
    outside = plant(os.path.join(sandbox, "outside", "gone_target.cpython-313.pyc"))
    link = os.path.join(in_root, "gone_link" + B.TAG)
    os.symlink(outside, link)
    linked_dir = os.path.join(in_root, "gone_linked_dir")
    os.symlink(os.path.dirname(outside), linked_dir)
    kept = [
        plant(os.path.join(in_root, "theme.cpython-39.pyc")),
        plant(theme + ".67890"),
        plant(os.path.join(in_root, "notes.txt")),
        plant(os.path.join(in_root, "gone_untagged.pyc")),
        link, outside,
    ]

    r = prepare(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " %d pruned" % len(gone) in r.stdout, r.stdout
    left = [p for p in gone if os.path.lexists(p)]
    assert not left, "not pruned: %s" % left
    lost = [p for p in kept if not os.path.lexists(p)]
    assert not lost, "pruned what it must keep: %s" % lost
    assert os.path.islink(linked_dir), "a symlinked directory was removed"
    assert not os.path.exists(os.path.join(in_root, "gone_pkg")), \
        "an emptied directory was left"
    assert os.path.isdir(os.path.join(sandbox, "src")), \
        "removed a directory outside the prefix"
    now = snapshot(prefix)
    changed = [p for p in settled if now.get(p) != settled[p]]
    assert not changed, "current bytecode changed: %s" % changed[:10]

    # Nothing more the second time.
    r = prepare(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 0 pruned" in r.stdout, r.stdout

    # A file that cannot be removed is reported; the step still succeeds.
    stuck = plant(B.cached_path(prefix, os.path.join(B.ROOT, "locked", "gone.py")))
    os.chmod(os.path.dirname(stuck), 0o500)
    try:
        r = prepare(installer)
    finally:
        os.chmod(os.path.dirname(stuck), 0o700)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 0 pruned" in r.stdout, r.stdout
    assert "could not prune " + stuck in r.stderr, r.stderr
    assert os.path.exists(stuck)

    assert B.tree_pycache() == before, sorted(B.tree_pycache() - before)
finally:
    B.remove(sandbox)

print("ok")
