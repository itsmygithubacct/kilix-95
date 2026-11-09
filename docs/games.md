# Kilix 95 games

How the Games menu finds, installs and launches games. Moved from the [README](../README.md).

## Games

The Games menu is backed by `games.py`. Some entries are built-in desktop games,
while others are installed on demand under user data directories.

Every entry defaults to enabled. The Games tab in kilix Settings and the
`kilix settings` TUI select which entries appear. For scripts,
`kilix games list` shows the current states; use
`kilix games disable doom kilix-pong` or `kilix games enable doom` to change
them.
Those choices live in `~/.local/gpu_terminal/settings.conf`; the separate
provider-private `games.conf` continues to record only installation paths.

The installers avoid writing into this checkout. Downloaded archives that ship
with pinned checksums are verified before use, and tar extraction rejects unsafe
paths, links, devices, and FIFOs.

Games and optional apps currently include Doom/DOSBox paths plus terminal or
Kitty-graphics projects such as Bashed Earth, Kilix JPAK, Kilix Rancher, Kilix
Pong, Kilix Lights, Super Kilix, Joustix, Chess Bash, Kilix Fishtank, Terminal
Lander, Kitty Brokeout, and kilix-amp support.

Game readiness checks are conservative. `games.py` first looks for a configured
working install, then for tools already on `$PATH`, then for previously vendored
assets under user data. Only if those paths fail does it offer an installer.

The installer path is designed for visible progress:

1. the desktop opens a tab or installer window;
2. stdout/stderr are captured into a short log;
3. successful setup records paths in `games.conf`;
4. failure leaves a readable error instead of closing silently.

Doom/DOSBox support writes a DOSBox config tuned for full-pane display and sound.
Native terminal/Kitty-graphics games are fetched at full immutable commit SHAs
and built under user data with `make`. Existing source caches must retain the
expected origin, pinned HEAD, and a clean tracked worktree. Build failures
include a dependency hint in the error text.
An explicitly configured different `dir` in `games.conf` remains user-managed
and is treated as a trusted local executable rather than a Kilix-managed cache.

Because these are optional downloads and builds, a fresh Plebian-OS image should
still boot the desktop and pass the core UI tests without preinstalling every
game dependency.
