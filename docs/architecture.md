# Kilix 95 architecture

How Kilix 95 relates to its Kilix host, how it renders and takes input, and which module does what. Moved from the [README](../README.md).

## Relationship To Kilix

Kilix 95 is the authoritative desktop-provider checkout, intentionally hosted
by Kilix. The copy bundled in Kilix is a compatibility fallback; the launcher
reports which one it selected instead of silently preferring a divergent tree.
The Kilix launcher passes `KILIX_HOME` so this repo can use the host SDK and
launch helpers. If `KILIX_HOME` is unset, `host.py` checks
`${GPU_TERMINAL_SOURCE_HOME:-~/.local/gpu_terminal/sources}/kilix`, then the workspace sibling
`../../kilix` checkout. Its final fallback is the canonical source-root path.

The boundary is:

- `kilix_sdk.term`: raw mode and terminal input parsing.
- `kilix_sdk.graphics`: inline Kitty graphics for streamed sessions.
- `kilix_sdk.state`: bounded, CRC-checked, crash-safe internal state records.
- Kilix CLI helpers: `kilix run`, `kilix open-url`, `kilix serve`.
- Kitty remote control: `kitten @ launch` for new tabs and windows.

`provider.json` declares provider API 1, the required `kilix_sdk` 1.13 contract,
and the security behaviors the provider implements. Kilix validates that
data-only manifest and its implementation markers before executing the
provider. `main.py` also calls `kilix_sdk.require_compatible("1.13")` as a
defense-in-depth runtime check. Incompatible hosts fail early with a clear
version error.

Everything specific to the desktop lives here: the shell, taskbar, window
manager, widgets, built-in apps, Help, System Manual browser, games registry,
and tests.

## How Rendering Works

The desktop owns a single RGB framebuffer. On every dirty frame it draws:

1. the wallpaper and desktop icons;
2. normal and modal windows;
3. the taskbar;
4. menus, switcher overlays, tooltips, and cursor;
5. startup/shutdown/BSOD system screens when active.

The framebuffer is blitted through the Kitty graphics protocol:

- Local Kilix sessions write frame bytes to private files under
  `~/.local/gpu_terminal/kilix-95/session` and place them with Kitty `t=t`.
- Streamed `kilix serve` sessions use inline `t=d` when `KILIX_STREAM=1`.
- tmux passthrough is handled when `KILIX_STREAM=1` and `TMUX` are set.

Input uses the Kitty keyboard protocol plus SGR-pixel mouse reporting
(`?1003h` and `?1016h`). Mouse coordinates therefore map directly onto
framebuffer pixels.

A bare tap of the Super (Windows) key toggles the Start menu, as does
`Ctrl+Escape`. Only a clean press-and-release counts: any other key or click
while Super is held disarms the tap, so `Super`+key combinations pass through
untouched.

Rendering is damage-driven. The event loop repaints only when something marks
the desktop dirty: input, resize, clock tick, caret blink, window/app updates,
screen saver changes, or periodic keepalive.

## Main Modules

| file | role |
|---|---|
| `main.py` | entry point, `Desk`, raw-mode lifecycle, input dispatch, render loop, blitting, screenshots |
| `theme.py` | Win95/XP identity, palettes, metrics, fonts, bevel primitives |
| `icons.py` | original pixel icons drawn on a 16x16 grid |
| `widgets.py` | retained widget toolkit: buttons, fields, text areas, lists, grids, menus, tabs, scrollbars |
| `wm.py` | window chrome, z-order, focus, modality, move/resize, dialogs |
| `taskbar.py` | Start menu, Help/System/Find menus, task buttons, quick launch, tray, clock |
| `shell.py` | desktop surface, launcher files, file associations, spawn verbs, browser/default-browser paths |
| `xdgapps.py` | freedesktop `.desktop` discovery and Start menu grouping |
| `games.py` | Games registry, on-demand installers, CLI launcher |
| `recycle.py` | recycle-bin backing store |
| `clipboard.py` | clipboard hub across desktop widgets, host X, and XPane displays |
| `vbox.py` | VirtualBox launcher detection and VM command construction |
| `apps/` | built-in windows such as File Manager, Settings, Help, System Manual, Notepad, Paint, WordPad, XPane |

Input dispatch order is:

```text
Desk -> MenuHost | drag owner | active/window hit | taskbar | shell
```

Windows capture the pressed widget until release. That is why buttons,
scrollbars, text selections, window drags, and list gestures keep working even
when the pointer moves during a drag.
