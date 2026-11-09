# Kilix 95 launch modes and launchers

How Kilix 95 starts programs (tabs, OS windows, `kilix run`, XPane, browsers) and how the desktop folder and `.desktop` launchers work. Moved from the [README](../README.md).

## Launch Modes

Kilix 95 has several launch paths, each with a different containment model.

| mode | used by | behavior |
|---|---|---|
| `tab` | terminal apps, explicitly terminal launchers | `kitten @ launch --type=tab` |
| `window` | launcher option | `kitten @ launch --type=os-window` |
| `run` | X11 apps, imported GUI launcher default | `kilix run COMMAND` in a Kilix tab |
| `fullscreen` | X11 app launcher option | XPane fullscreen-sized app window |
| `browse` | URL launcher files | selected browser via `kilix run --fill` |
| default browser | Help links | selected browser via `kilix run --fill` |

The explicit Firefox and Chromium program entries default to filled `kilix run`
tabs so they stay contained in the terminal pane. General URLs use the first
installed real browser in the documented order and contain it the same way;
Kilix's in-pane URL renderer is the no-browser fallback.
Contained Chromium and Firefox instances use disposable per-window profiles so
an already-running native browser cannot capture the URL. Launch from a
terminal with an explicit Chromium `--user-data-dir` or Firefox `--profile`
when persistent browser state is required.

VirtualBox is special-cased. `.vbox` files and VirtualBox `.desktop` entries
open through `kilix run --refit-windows` so the VM window stays contained.

## Desktop Folder And Launchers

The desktop folder is:

```text
~/.local/gpu_terminal/kilix-95/data/desktop
```

Override it with:

```bash
KILIX_DESKTOP_DIR=/path/to/desktop kilix desktop
```

Real files and directories in this folder appear as icons. `.desktop` files,
including those created by **Create Launcher...**, appear as shortcuts.

Launcher example:

```ini
[Desktop Entry]
Type=Application
Name=htop
Exec=htop
Path=~/
Icon=terminal
X-Kilix-Open=tab
```

Supported `X-Kilix-Open` values:

- `tab`: run in a Kilix tab.
- `window`: run in a Kilix OS window.
- `run`: run an X11 app through `kilix run`.
- `fullscreen`: run as a full-desktop XPane window.
- `browse`: open a URL in the selected browser through `kilix run --fill`.

An imported application launcher with no `X-Kilix-Open` uses `run` unless it
declares `Terminal=true`, in which case it uses `tab`. Freedesktop `%U`, `%F`,
and related argument placeholders are removed before a copied launcher runs;
Kilix 95 supplies no selected-file arguments for them.

For URL launchers:

```ini
[Desktop Entry]
Type=Link
Name=Project page
URL=https://example.invalid/
Icon=browser
```
