# Kilix 95 runtime state and environment variables

Where Kilix 95 keeps its state and user data, how to reset it, and the environment variables it reads. Moved from the [README](../README.md).

## Runtime State And User Data

Runtime state is intentionally outside the repo.

| data | default location |
|---|---|
| desktop folder | `~/.local/gpu_terminal/kilix-95/data/desktop` |
| desktop state | `~/.local/gpu_terminal/kilix-95/state/shell.state` |
| recycle bin | `$KILIX_RECYCLE_DIR`, beside `$KILIX_DESKTOP_DIR`, or `~/.local/gpu_terminal/kilix-95/data/recycled` |
| generated/bundled sound cache | `~/.local/gpu_terminal/kilix-95/data/sounds` |
| themes and virtual CD | `~/.local/gpu_terminal/kilix-95/data/themes`, `data/virtual-cd` |
| Briefcase data and sync record | `~/.local/gpu_terminal/kilix-95/data/briefcase`, `state/briefcase.state` |
| nostalgia/network/printer definitions | `~/.local/gpu_terminal/kilix-95/config/nostalgia.json` |
| game install paths | `~/.local/gpu_terminal/kilix-95/config/games.conf` |
| game/app downloads | `~/.local/gpu_terminal/kilix-95/data/games`, `~/.local/gpu_terminal/kilix-95/data/apps` |
| Kilix-Amp runtime | `config/app-state`, `data/app-state`, `state/app-state`, and `cache/app-state` below the Kilix 95 storage root |
| desktop frames and installer logs | `~/.local/gpu_terminal/kilix-95/session` |
| Python bytecode cache | `~/.local/gpu_terminal/kilix-95/cache/pycache` |
| Kitty/Kilix settings | `$KITTY_CONFIG_DIRECTORY/kitty.conf`, else `~/.local/gpu_terminal/kilix/config/kitty.conf` |
| Shared chrome and game availability | `~/.local/gpu_terminal/settings.conf` (`$GPU_TERMINAL_SETTINGS_FILE` overrides it) |

Settings is the most important host mutation: it edits the active Kitty/Kilix
configuration, not only desktop-local state.

Most user data can be reset independently:

- Delete `state/shell.state` to reset desktop layout, flavor, recent
  documents, first-run Help state, volume, and wallpaper choices. After an
  upgrade, also remove the retained desktop `.state.json` recovery copy if you
  do not want it imported again.
- Remove or point `KILIX_DESKTOP_DIR` elsewhere to test with a fresh desktop
  folder.
- Empty the recycle directory only when you intentionally want to permanently
  discard recycled files.
- Delete generated sound caches if bundled sound assets or synth output need to
  regenerate; sound schemes live beside them and should be preserved when they
  are user-authored.
- Game installs are disposable caches, but `games.conf` records discovered or
  installed paths and should be kept if the user configured custom locations.

Tests rely on this separation. The harness sets `KILIX_DESKTOP_DIR` to a temp
folder, which also isolates the default recycle bin beside that folder.

## Environment Variables

| variable | effect |
|---|---|
| `KILIX_HOME` | host Kilix checkout |
| `GPU_TERMINAL_SOURCE_HOME` | shared source root (default `~/.local/gpu_terminal/sources`) |
| `GPU_TERMINAL_HOME` | shared writable root (default `~/.local/gpu_terminal`) |
| `GPU_TERMINAL_SETTINGS_FILE` | shared chrome/game config (default `$GPU_TERMINAL_HOME/settings.conf`) |
| `KILIX95_STORAGE_HOME` | Kilix 95 writable root override |
| `KILIX95_CONFIG_HOME`, `KILIX95_STATE_HOME`, `KILIX95_CACHE_HOME`, `KILIX95_DATA_HOME`, `KILIX95_SESSION_HOME` | individual Kilix 95 storage-category overrides |
| `KILIX_DESKTOP_DIR` | desktop folder override |
| `KILIX_RECYCLE_DIR` | recycle-bin override |
| `KILIX_DESKTOP_FLAVOR` | `95` or `xp` first-launch flavor |
| `KILIX_FLAVOR` | fallback flavor selector |
| `KILIX_STREAM=1` | inline graphics mode for streamed sessions |
| `KILIX_NO_SOUND=1` | disable UI sound playback |
| `KILIX_HOST_CLIP=0` | disable host clipboard bridge |
| `KILIX_XPANE_WM=0` | disable XPane's minimal EWMH bridge |
| `KILIX_STARTUP_SCREEN_SECONDS` | startup screen duration clamp override |
| `KILIX_SHUTDOWN_SCREEN_SECONDS` | shutdown screen duration clamp override |
| `MANPATH` | manual page roots for System Manual |
| `KITTY_CONFIG_DIRECTORY` | settings file directory |
| `KITTY_LISTEN_ON` | required for Kitty remote-control launches |
| `KITTY_PID` | fallback reload signal target for Settings |

Common development examples:

```bash
# fresh, isolated desktop state
KILIX_DESKTOP_DIR=$(mktemp -d) KILIX_HOME=~/.local/gpu_terminal/sources/kilix \
  python3 main.py

# XP flavor screenshot without changing saved state
KILIX_DESKTOP_FLAVOR=xp KILIX_HOME=~/.local/gpu_terminal/sources/kilix \
  python3 main.py --screenshot /tmp/xp.png --scene desktop

# disable sound while debugging UI behavior
KILIX_NO_SOUND=1 KILIX_HOME=~/.local/gpu_terminal/sources/kilix python3 main.py

# test System Manual against a controlled manpath
MANPATH=/tmp/test-man KILIX_HOME=~/.local/gpu_terminal/sources/kilix python3 main.py
```

Variables set by the host environment, such as `KITTY_LISTEN_ON`,
`KITTY_WINDOW_ID`, `KITTY_CONFIG_DIRECTORY`, `DISPLAY`, `TMUX`, and
`KILIX_STREAM`, should generally be inherited from Kilix rather than invented by
tests or launch scripts unless the test is explicitly about that path.
