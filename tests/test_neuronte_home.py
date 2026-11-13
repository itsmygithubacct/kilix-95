"""Where the desktop finds Neuronte: NEURONTE_HOME, else the installed copy.

On an installed system Neuronte sits with the other installed sources, in
$GPU_TERMINAL_SOURCE_HOME/neuronte, which is
~/.local/gpu_terminal/sources/neuronte unless that variable is set. Each
case runs in a fresh interpreter because the root is read at import.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.dirname(HERE)
CLEARED = ("NEURONTE_HOME", "NEURONTE_LIB", "GPU_TERMINAL_SOURCE_HOME")


def run(code, **env):
    base = {k: v for k, v in os.environ.items() if k not in CLEARED}
    base.update(env)
    base["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=base,
                          capture_output=True, text=True)
    assert done.returncode == 0, (env, done.stdout, done.stderr)
    return done.stdout.strip()


def root(**env):
    return run("import sys; sys.path.insert(0, %r)\n"
               "import neuronte_face as N; print(N._ROOT)" % DESKTOP, **env)


with tempfile.TemporaryDirectory(prefix="k95-neuronte-home-") as tmp:
    home = os.path.join(tmp, "home")
    installed = os.path.join(home, ".local", "gpu_terminal", "sources", "neuronte")
    sources = os.path.join(tmp, "sources")
    checkout = os.path.join(tmp, "checkout")

    # Nothing set: the installed copy under ~/.local, beside the others.
    assert root(HOME=home) == installed, root(HOME=home)
    # The source home Kilix 95 uses for its other installed parts.
    assert root(HOME=home, GPU_TERMINAL_SOURCE_HOME=sources) == \
        os.path.join(sources, "neuronte")
    assert root(HOME=home, GPU_TERMINAL_SOURCE_HOME="~/src") == \
        os.path.join(home, "src", "neuronte")
    # An explicit checkout wins over both.
    assert root(HOME=home, GPU_TERMINAL_SOURCE_HOME=sources,
                NEURONTE_HOME=checkout) == checkout
    # An empty value counts as unset, as it does for the source home.
    assert root(HOME=home, NEURONTE_HOME="", GPU_TERMINAL_SOURCE_HOME="") == installed

    # An installed directory with weights but no library keeps the DejaVu
    # chrome and the drawn flame, the same as no Neuronte at all.
    os.makedirs(os.path.join(sources, "neuronte", "weights"))
    with open(os.path.join(sources, "neuronte", "weights", "neuronte-ui11-v0.nrt"), "wb"):
        pass
    out = run("import harness\n"
              "from PIL import ImageFont\n"
              "import neuronte_face as N, neuronte_flame as F, theme as T\n"
              "assert N._ROOT == %r, N._ROOT\n"
              "assert N._library() is None\n"
              "assert all(isinstance(f, ImageFont.FreeTypeFont) for f in (T.FONT, T.BOLD, T.SMALL))\n"
              "assert F.image(16) is None\n"
              "print('fallback ok')" % os.path.join(sources, "neuronte"),
              HOME=home, GPU_TERMINAL_SOURCE_HOME=sources)
    assert out.endswith("fallback ok"), out

print("ok")
