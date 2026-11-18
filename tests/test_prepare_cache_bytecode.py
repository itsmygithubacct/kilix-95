"""`main.py --prepare-cache` writes the bytecode a first start would otherwise compile.

Plebian-OS runs it as the desktop user after installing or updating Kilix 95
and the Kilix SDK. It must write every .pyc the next start reads, at the paths
the desktop's imports compute, so that start, launched as the Kilix launcher
launches it, compiles nothing. It writes no bytecode for system modules apart
from those loaded before main.py (Debian's own bytecode serves the rest) and
creates no __pycache__ in either tree. A second run finds everything current
and rewrites nothing; a damaged or stale file is rewritten; a file that
cannot be written makes it exit 1.
"""
import os
import subprocess
import sys

import bytecode_check as B


def precompile(env):
    return subprocess.run(
        [sys.executable, os.path.join(B.ROOT, "main.py"), "--prepare-cache"],
        env=env, cwd=sandbox, capture_output=True, text=True, timeout=120)


def snapshot(prefix):
    out = {}
    for directory, _dirs, files in os.walk(prefix):
        for name in files:
            path = os.path.join(directory, name)
            st = os.stat(path)
            out[path] = (st.st_mtime_ns, st.st_size, st.st_ino)
    return out


sandbox = B.scratch("precompile")
try:
    before = B.tree_pycache()
    cache = os.path.join(sandbox, "cache")
    prefix = os.path.join(cache, "pycache")
    # The installer's environment: no PYTHONPYCACHEPREFIX, just the storage rules.
    installer = B.env_for(cache, launcher=False)
    r = precompile(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 failed" in r.stdout and prefix in r.stdout, r.stdout

    sources = B.prefix_sources(prefix)
    own = [os.path.join(d, f)
           for top in ("", "apps")
           for d in [os.path.join(B.ROOT, top)]
           for f in sorted(os.listdir(d)) if f.endswith(".py")]
    sdk = [os.path.join(d, f) for d, _ds, fs in
           os.walk(os.path.join(B.KILIX_HOME, "config")) for f in fs
           if f.endswith(".py") and "__pycache__" not in d]
    missing = [s for s in own + sdk if s not in sources]
    assert not missing, "not precompiled: %s" % missing[:20]
    assert not any(s.startswith(os.path.join(B.ROOT, "tests") + os.sep)
                   for s in sources), "tests/ was compiled"
    # The pinned packages the SDK loads (kilix_state at least), each whole.
    pinned = [s for s in sources if B.in_trees(s) and
              os.path.join(os.sep, "third_party", "") in s]
    assert any("/kilix_state/" in s for s in pinned), pinned[:10]
    packages = set()
    for s in pinned:
        top = os.path.dirname(s)
        while os.path.isfile(os.path.join(os.path.dirname(top), "__init__.py")):
            top = os.path.dirname(top)
        packages.add(top)
    whole = [os.path.join(d, f) for p in sorted(packages)
             for d, ds, fs in os.walk(p) for f in fs
             if f.endswith(".py") and "__pycache__" not in d]
    missing = [s for s in whole if s not in sources]
    assert not missing, "pinned package files not precompiled: %s" % missing[:20]
    assert len(whole) > len(packages), whole

    # Only these system modules: what the interpreter loaded before main.py.
    launch_probe = subprocess.run(
        [sys.executable, "-c",
         "import sys; print('\\n'.join(m.__file__ for m in list(sys.modules.values())"
         " if isinstance(getattr(m, '__file__', None), str)))"],
        env=installer, capture_output=True, text=True, timeout=30)
    launch = {os.path.abspath(f) for f in launch_probe.stdout.split()}
    stray = [s for s in sources if not B.in_trees(s) and s not in launch]
    assert not stray, "system bytecode written to the prefix: %s" % stray

    # The next start, launched as the launcher launches it, compiles nothing.
    first = snapshot(prefix)
    work = os.path.join(sandbox, "run")
    os.makedirs(work)
    B.start(B.env_for(cache), work)
    compiled = sorted(set(snapshot(prefix)) - set(first))
    assert not compiled, "the first start still compiled:\n  " + \
        "\n  ".join(compiled)

    # Idempotent: everything is current, nothing is rewritten.
    settled = snapshot(prefix)
    r = precompile(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 0 written" in r.stdout, r.stdout
    assert snapshot(prefix) == settled, "a current .pyc was rewritten"

    # A damaged file (here: a stale header) is rewritten, and only that one.
    # An application start-up does not import, so the rewrite is this step's
    # own and not the importer's.
    victim = B.cached_path(prefix, os.path.join(B.ROOT, "apps", "wordpad.py"))
    with open(victim, "r+b") as fh:
        fh.seek(8)
        fh.write(b"\0\0\0\0")
    r = precompile(installer)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 1 written" in r.stdout, r.stdout
    after = snapshot(prefix)
    assert after[victim][2] != settled[victim][2], "wordpad bytecode not replaced"
    assert {p for p in after if after[p] != settled[p]} == {victim}

    # A file that cannot be written fails the step: exit 1, the file named on
    # stderr, everything else still current.
    os.unlink(victim)
    apps_cache = os.path.dirname(victim)
    os.chmod(apps_cache, 0o500)
    try:
        r = precompile(installer)
    finally:
        os.chmod(apps_cache, 0o700)
    assert r.returncode == 1, (r.returncode, r.stdout + r.stderr)
    assert " 0 written" in r.stdout and " 1 failed" in r.stdout, r.stdout
    assert os.path.join(B.ROOT, "apps", "wordpad.py") in r.stderr, r.stderr
    assert not os.path.exists(victim)

    assert B.tree_pycache() == before, sorted(B.tree_pycache() - before)
finally:
    B.remove(sandbox)

print("ok")
