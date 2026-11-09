# Developing Kilix 95

Runtime requirements and the test suite. Moved from the [README](../README.md).

## Requirements

This repository does not currently ship packaging metadata such as
`pyproject.toml` or a requirements file. The surrounding Kilix/Plebian-OS
provisioning is expected to install the runtime dependencies.

Common requirements by feature:

- Python 3
- Pillow
- Kilix checkout with `config/kilix_sdk`
- Kitty/kitten remote control
- ffmpeg for XPane capture
- Xvfb and XTest support for XPane
- python-xlib for XPane and clipboard bridging
- `man`/`manpath` for System Manual
- Google Chrome, Chromium, or Firefox for real-browser links
- audio players such as `paplay`, `ffplay`, or `play` for UI sounds
- browsers/VirtualBox only when those launch paths are used

Dependency failures should degrade by feature:

- missing `man` affects only System Manual;
- missing real browsers activates Kilix's in-pane URL fallback;
- missing audio players mutes UI sounds;
- missing Xvfb/ffmpeg/python-xlib affects XPane and GUI app embedding;
- missing browser binaries affects browser launch entries;
- missing Kitty remote control affects tab/window launches.

This split is deliberate. The desktop should still render, handle input, open
built-in pure-Python apps, and show useful error dialogs when optional host
features are absent.

For provisioning, install dependencies at the Plebian-OS/Pleb layer rather than
vendoring them into this repo. This keeps Kilix 95 as a desktop source checkout
with user state and system packages managed by the surrounding system.

## Testing

Run the full suite:

```bash
python3 tests/run.py
```

The test runner executes each `test_*.py` in a fresh subprocess and gives it a
temporary `KILIX_DESKTOP_DIR`. Most tests construct an offscreen `Desk(term=None)`
and feed synthetic widget/input events, so they do not require taking over the
terminal.

Focused checks:

```bash
python3 tests/test_winhelp.py
python3 tests/test_manual.py
python3 tests/test_shell_xpane.py
python3 tests/test_start_help_menu.py
```

Render screenshot fixtures:

```bash
KILIX_HOME=~/.local/gpu_terminal/sources/kilix \
  python3 main.py --screenshot /tmp/shot.png --scene all
```

Test style:

- Tests are plain Python scripts, not pytest modules.
- Each script should be runnable directly with `python3 tests/test_name.py`.
- Use `tests/harness.py` for offscreen desks and synthetic input events.
- Prefer temp directories and monkeypatching over touching the real desktop,
  manpath, recycle bin, or system apps.
- Keep integration launch tests at the shell boundary by stubbing `_tab`,
  `_popen`, `open_in_xpane`, or external discovery helpers.

When adding a desktop feature, add the narrowest test that proves the contract:

- menu entries: open Start offscreen and walk `MenuItem` trees;
- widgets/windows: construct a `Desk(term=None)`, add the window, and send
  synthetic key/mouse events;
- file behavior: isolate with temp dirs and environment overrides;
- host launch behavior: monkeypatch discovery/spawn methods and assert argv;
- parser behavior: feed raw bytes through the harness term helpers.

The full suite is intentionally fast enough to run before every commit.
