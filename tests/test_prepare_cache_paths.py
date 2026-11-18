"""`main.py --prepare-cache` writes where the desktop reads, under each storage rule.

The --prepare-cache step runs main.py's own storage bootstrap, so it resolves the
bytecode prefix exactly as a desktop start does: KILIX95_CACHE_HOME if set
(test_prepare_cache_bytecode.py), else KILIX95_STORAGE_HOME/cache, else
GPU_TERMINAL_HOME/kilix-95/cache. For the last two rules this compares the
directory a precompile writes with the one a real start writes, and checks the
private 0700 boundaries.
"""
import os
import stat
import subprocess
import sys

import bytecode_check as B

STORAGE = ("KILIX95_STORAGE_HOME", "KILIX95_CONFIG_HOME", "KILIX95_STATE_HOME",
           "KILIX95_CACHE_HOME", "KILIX95_DATA_HOME", "KILIX95_SESSION_HOME")


def run(env, *args):
    return subprocess.run([sys.executable, os.path.join(B.ROOT, "main.py"), *args],
                          env=env, cwd=sandbox, capture_output=True, text=True,
                          timeout=120)


def written(root):
    """Directories holding Kilix 95's own theme.pyc below root."""
    return sorted(d for d, _ds, fs in os.walk(root)
                  for f in fs if f.startswith("theme.") and f.endswith(B.TAG)
                  and B.ROOT in d)


sandbox = B.scratch("precompile-paths")
try:
    for rule in ("gpu-terminal-home", "storage-home"):
        base = os.path.join(sandbox, rule)
        env = {k: v for k, v in B.env_for(os.path.join(base, "unused"),
                                          launcher=False).items()
               if k not in STORAGE}
        env["GPU_TERMINAL_HOME"] = os.path.join(base, "gpu")
        if rule == "storage-home":
            env["KILIX95_STORAGE_HOME"] = os.path.join(base, "own-k95")
            storage = env["KILIX95_STORAGE_HOME"]
        else:
            storage = os.path.join(base, "gpu", "kilix-95")
        prefix = os.path.join(storage, "cache", "pycache")

        r = run(env, "--prepare-cache")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "(%s)" % prefix in r.stdout, (rule, r.stdout)
        ahead = written(base)
        assert len(ahead) == 1 and ahead[0].startswith(prefix + os.sep), (rule, ahead)
        for d in (storage, os.path.join(storage, "cache"), prefix):
            assert stat.S_IMODE(os.stat(d).st_mode) == 0o700, d

        # A desktop process with the same environment reads exactly there:
        # with the precompiled file removed it writes it back to the same path.
        victim = os.path.join(ahead[0], "theme" + B.TAG)
        os.unlink(victim)
        r = run(env, "--version")
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.exists(victim), (rule, written(base))
        assert written(base) == ahead, (rule, written(base))
    assert not os.path.exists(os.path.join(sandbox, "storage-home", "gpu",
                                           "kilix-95")), \
        "KILIX95_STORAGE_HOME was not honoured"
finally:
    B.remove(sandbox)

print("ok")
