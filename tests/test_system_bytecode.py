"""A start reads system modules from Debian's bytecode and keeps its own in the prefix.

main.py imports the system modules start-up uses (_SYSTEM_MODULES) before it
sets sys.pycache_prefix, so they load from the bytecode the distribution ships
instead of being compiled again into the Kilix 95 cache. Started the way the
Kilix launcher starts it, with PYTHONPYCACHEPREFIX set and an empty cache, an
interactive start must leave in the prefix only bytecode for Kilix 95, the
Kilix SDK and the modules the interpreter had loaded before main.py ran. It
must create no __pycache__ in either source tree. The list must not be wider
than start-up: the same start with the list emptied has to put every listed
module that exists on this Python into the prefix. Without that check, an
entry start-up no longer needs would go on being imported at every start.
(test_system_bytecode_display.py covers the modules a host display adds.)
"""
import os

import bytecode_check as B

sandbox = B.scratch("system-bytecode")
try:
    before = B.tree_pycache()

    # 1. As shipped: nothing from outside the two trees is compiled.
    cache = os.path.join(sandbox, "cache")
    work = os.path.join(sandbox, "run")
    os.makedirs(work)
    launch = set(B.start(B.env_for(cache), work))
    prefix = os.path.join(cache, "pycache")
    sources = B.prefix_sources(prefix)
    assert any(B.in_trees(s) for s in sources), sources       # it did compile
    stray = [s for s in sources if not B.in_trees(s) and s not in launch]
    assert not stray, (
        "start-up compiled these system modules into the Kilix 95 prefix; "
        "add their root import to main.py's _SYSTEM_MODULES:\n  "
        + "\n  ".join(stray))

    # 2. The list is no wider than start-up.
    cache2 = os.path.join(sandbox, "cache-unlisted")
    work2 = os.path.join(sandbox, "run-unlisted")
    os.makedirs(work2)
    launch2 = set(B.start(B.env_for(cache2), work2, empty_list=True))
    prefix2 = os.path.join(cache2, "pycache")
    unused, early = [], []
    for name in B.system_list():
        source = B.module_source(name)
        if source is None:
            continue                       # not installed on this Python
        if source in launch2:
            early.append(name)             # loaded before main.py: listing it does nothing
        elif not os.path.exists(B.cached_path(prefix2, source)):
            unused.append(name)
    assert not unused, (
        "main.py's _SYSTEM_MODULES names modules start-up does not import; "
        "remove them: %s" % unused)
    assert not early, (
        "main.py's _SYSTEM_MODULES names modules loaded before main.py: %s"
        % early)
    # and without the list, those system modules are what the prefix gets
    assert any(not B.in_trees(s) and s not in launch2
               for s in B.prefix_sources(prefix2))

    assert B.tree_pycache() == before, sorted(B.tree_pycache() - before)
finally:
    B.remove(sandbox)

print("ok")
