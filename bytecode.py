"""Write Kilix 95's bytecode ahead of time, for `python3 main.py --prepare-cache`.

Kilix 95 keeps the bytecode of its own modules and of the Kilix SDK under a
private prefix (<Kilix 95 cache>/pycache) so neither source tree gets a
__pycache__.  Without this step the first start after an install or an update
compiles them, and the applications compile on first open.  prepare_cache.py
runs this module from main.py, after main.py has resolved the prefix and put
the SDK on sys.path, so the files written here are the exact ones the
desktop's imports look for: same user, same interpreter, same absolute source
paths, same prefix.

What is compiled:
  * this checkout, except tests/ and tools/;
  * the SDK's config/ tree;
  * the package trees of the pinned packages the SDK loads (found from the
    modules it actually imports, not from a list kept here);
  * the modules the interpreter loaded before main.py.  The Kilix launcher
    sets PYTHONPYCACHEPREFIX, and those are read from the prefix too.
The standard library and dist-packages are not: main.py imports them before
it sets the prefix, from the bytecode Debian ships.

A file whose bytecode is already current is left alone, so running this again
is cheap.  Files are replaced atomically, so a desktop starting meanwhile
reads the old file or the new one.  A file that cannot be compiled is named
on stderr and makes the result 1; the installer treats that as a warning,
since the desktop compiles whatever is missing itself.
"""
import os
import sys
import threading

# py_compile is not a start-up import.  Load it from Debian's bytecode, as
# main.py does for start-up's own system modules, rather than leave a copy
# the desktop never reads in its prefix.  That briefly clears the prefix, so
# only when no other thread can be importing meanwhile (prepare_cache.py
# finishes the Neuronte letter thread first); otherwise import it as is.
if threading.active_count() == 1:
    _prefix, sys.pycache_prefix = sys.pycache_prefix, None
    try:
        import importlib.util
        import py_compile
        import struct
    finally:
        sys.pycache_prefix = _prefix
else:
    import importlib.util
    import py_compile
    import struct

SKIP_DIRS = {"tests", "tools"}          # top level of this checkout only
# The SDK modules through which Kilix 95 uses the SDK's pinned packages.
SDK_LOADERS = ("kilix_sdk.state", "kilix_sdk.graphics", "kilix_sdk.content")


def _sources(root, skip=()):
    out = []
    for directory, dirs, files in os.walk(root):
        top = os.path.normpath(directory) == os.path.normpath(root)
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(".") and d != "__pycache__"
                         and not (top and d in skip))
        out += [os.path.join(directory, f) for f in sorted(files)
                if f.endswith(".py")]
    return out


def _within(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _pinned_package_dirs(kilix_home):
    """Package directories under KILIX_HOME, outside config/, that the SDK loads."""
    import importlib
    for name in SDK_LOADERS:
        importlib.import_module(name)
    config = os.path.join(kilix_home, "config")
    roots = {kilix_home, os.path.realpath(kilix_home)}
    dirs = set()
    for module in list(sys.modules.values()):
        for location in getattr(module, "__path__", None) or ():
            location = os.path.abspath(location)
            if any(_within(location, r) for r in roots) and \
                    not _within(location, config) and \
                    not _within(location, os.path.realpath(config)):
                dirs.add(location)
    # a subpackage is compiled with its package
    return sorted(d for d in dirs
                  if not any(d != o and _within(d, o) for o in dirs))


def _launch_sources(launch_modules):
    out = []
    for name in launch_modules:
        spec = getattr(sys.modules.get(name), "__spec__", None)
        origin = getattr(spec, "origin", None)
        if spec is not None and spec.has_location and spec.cached and \
                isinstance(origin, str) and origin.endswith(".py") and \
                os.path.isfile(origin):
            out.append(origin)
    return out


def _current(source, cfile):
    """True when cfile is a timestamp .pyc that matches source (as the importer checks)."""
    try:
        st = os.stat(source)
        with open(cfile, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    expect = importlib.util.MAGIC_NUMBER + struct.pack(
        "<4sLL", b"\0\0\0\0", int(st.st_mtime) & 0xFFFFFFFF,
        st.st_size & 0xFFFFFFFF)
    return head == expect


def compile_all(sources):
    written = current = 0
    failed = []
    for source in sources:
        cfile = importlib.util.cache_from_source(source)
        if _current(source, cfile):
            current += 1
            continue
        try:
            py_compile.compile(
                source, cfile=cfile, doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            written += 1
        except (py_compile.PyCompileError, OSError, ValueError) as error:
            failed.append((source, error))
    return written, current, failed


def compile_desktop(prefix, here, kilix_home, launch_modules):
    """Compile everything listed above into prefix; 0, or 1 if anything failed."""
    if not prefix or sys.pycache_prefix != prefix:
        print("kilix-95 bytecode: the bytecode prefix is not set", file=sys.stderr)
        return 1
    sources = _sources(here, SKIP_DIRS)
    sources += _sources(os.path.join(kilix_home, "config"))
    try:
        for directory in _pinned_package_dirs(kilix_home):
            sources += _sources(directory)
    except Exception as error:      # still compile everything else
        print(f"kilix-95 bytecode: SDK packages not found: {error}",
              file=sys.stderr)
        sources.append(None)
    sources += _launch_sources(launch_modules)
    seen, unique = set(), []
    for source in sources:
        if source is not None and source not in seen:
            seen.add(source)
            unique.append(source)
    written, current, failed = compile_all(unique)
    for source, error in failed:
        print(f"kilix-95 bytecode: {source}: {error}", file=sys.stderr)
    print(f"kilix-95 bytecode: {len(unique)} files, {written} written, "
          f"{current} already current, {len(failed)} failed ({prefix})")
    return 1 if failed or None in sources else 0
