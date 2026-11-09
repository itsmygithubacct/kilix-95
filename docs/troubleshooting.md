# Kilix 95 troubleshooting

Common failures and what to check. Moved from the [README](../README.md).

## Troubleshooting

**Start menu opens but launching a tab fails**

Check that `KITTY_LISTEN_ON` is set and that `kitten` is reachable from the
Kilix checkout or `$PATH`.

If this happens only outside Kilix, it is expected: tab/window launches require
Kitty remote control from a live Kilix/Kitty session. Use screenshot mode or
offscreen tests for noninteractive development.

**System Manual is empty**

Check that manual pages are installed and that `manpath -q` returns useful
roots. If needed, set `MANPATH` explicitly before launching the desktop.

Also check that the man directories contain section folders such as `man1`,
`man5`, or `man8`, and files named like `bash.1.gz` or `ssh_config.5.gz`.

**Help links do not open**

Install Google Chrome (`google-chrome` or `google-chrome-stable`), Chromium
(`chromium` or `chromium-browser`), or Firefox (`firefox-esr` or `firefox`).
Kilix 95 checks for them in the order documented under Help. If none is
installed, URL launchers and Help links fall back to the experimental in-pane
browser.

If a browser exists but nothing appears, reproduce the contained path from a
regular terminal with `kilix run --fill BROWSER URL`, substituting the selected
browser command.

**X11 apps fail to open in desktop windows**

Check for Xvfb, ffmpeg, python-xlib, XTest support, and an available browser/app
binary. XPane failures should show an error dialog instead of killing the
desktop.

**Settings saves but the terminal does not change**

The config file was written, but live reload failed. Use Kitty's reload action
manually or restart Kilix.

Check whether `KITTY_LISTEN_ON` is set for `kitten @ action load_config_file`.
If it is not, Settings tries `SIGUSR1` through `KITTY_PID`. If neither is
available, saved changes will apply on the next Kilix restart.

**A file opens in the wrong app**

File associations are centralized in `shell.py`. Check the extension routing in
`open_path()` and the launcher handling for `.desktop` files before changing an
individual app.

**Recycle Bin restore lands at a different name**

Restore avoids overwriting existing files. If the original path is occupied, the
restored item gets a disambiguated name like `file (2).txt`.

**A game installer fails**

Read the installer tab/log text first. Network failures, checksum mismatches,
missing compilers, and missing development libraries should be reported there.
Installed or partially installed assets live under user data, not the repo.

**The desktop appears blank or mis-sized**

Resize the terminal once, or run a screenshot scene to separate rendering
problems from terminal graphics transport problems:

```bash
KILIX_HOME=~/.local/gpu_terminal/sources/kilix \
  python3 main.py --screenshot /tmp/shot.png --scene desktop
```
