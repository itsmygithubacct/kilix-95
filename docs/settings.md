# Kilix 95 Settings app

What the Settings app edits, where it writes, and how it reloads Kilix live. Moved from the [README](../README.md).

## Settings App

The Settings app edits the active `kitty.conf`, desktop preferences, and the
stack-wide clickable-chrome settings.

It normally writes:

```text
$KITTY_CONFIG_DIRECTORY/kitty.conf
```

or, when that variable is absent:

```text
~/.local/gpu_terminal/kilix/config/kitty.conf
```

The Kilix launcher creates that user file with a relative include of its
managed `.kilix-defaults.conf` link. The launcher refreshes the link after a
checkout move. Settings atomically writes only the user file and never dirties
the host checkout.

The Top bar, Pane buttons, Session logs, and Games tabs write the
non-executable shared source
of truth at `~/.local/gpu_terminal/settings.conf`. They can independently
remove and re-add the default-off thermometer, volume, network/Wi-Fi, calendar,
date/time, battery, the `auto`/`always`/`off` pane-CPU and pane-memory sides,
synchronized-input keyboard button, font-size,
four-way split, maximize, close, and every Kilix game.

The **Session logs** tab controls Kilix's default-on pane transcripts: whether
output is recorded at all, whether kitty graphics payloads are elided to a
marker or kept verbatim, and the per-pane size budget (`2M`/`8M`/`32M`/`128M`).
The same three settings are available as `kilix settings --set transcript=off`,
`--set transcript_graphics=keep`, and `--set transcript_size=32M`, and in the
`kilix settings` TUI under Session logging. Recorded panes are listed with
`kilix transcript`. The same game choices
are available in the `kilix settings` TUI and with the commands
`kilix games list`, `kilix games enable`, and `kilix games disable`. The
thermometer shows the hottest sensor in green/yellow/red and opens Kilix Temps
in a graphical tab. An installed command is preferred over development source;
on a fresh stack the menu delegates to Kilix's pinned, verified dashboard
installer. The volume item opens `pulsemixer` (falling back to
`alsamixer`); the network item is immediately left of the calendar and opens
NetworkManager's `nmtui`. Start ▸ Programs ▸ Kilix Temps launches the same
resolved graphical dashboard.
Start ▸ Programs ▸ Kilix Memory launches the RAM, swap, PSI pressure, paging,
and per-process dashboard in a graphical tab. The shared pane resource chip
opens the same monitor. CPU load is left of the chip (`auto` above `1.0`), and
pane RAM is right (`auto` above 1 GiB); `always` and `off` override either side
independently.

The **Voice** tab lists every shared speech-model choice and provides an
**Install + use model** action. It opens Kilix's verified installer in a visible
terminal tab; the child makes the model and its compatible recognizer the
default only after installation succeeds. Merely opening Settings or changing
the dropdown downloads nothing. The small and lgraph English models run through
Vosk. The shared VibeVoice weights can be installed/defaulted through Bonsai,
while the current live voice runtime marks them unsupported rather than
pretending dictation is ready.

Start ▸ Programs ▸ **BitNet Models** opens the Kilix Bonsai model store: the
1-bit and 1.58-bit models this stack can run, what each costs to download, and
what is already on disk. It resolves an installed `kilix-bonsai` first and
otherwise delegates to `kilix bonsai`, which installs the pinned closure, so
the menu entry and the command can never run different builds — and neither
prefers a source checkout over the pin. Opening it with nothing downloaded is
the normal case — the first screen prices each model and offers to fetch one.
One of them is the dictation engine, and both it and Dictation read the same
copy.

Start ▸ Programs ▸ **PTY Sessions** opens the graphical persistent-pane manager.
It lists attached, detached and unreachable sessions, previews output read-only,
shows archived journals, and ends a selected session after confirmation with an
identity-bound receipt. Calls run off the UI thread with bounded waits.
**PTY Sessions (Terminal)** remains available under Tools and opens the existing
unbrokered terminal manager. These manage terminal processes; `kilix session`
is the separate managed coding-run launcher.

The Tools tab reports whether tmux-cli's `tb` command is available and offers
an **Install / repair tb** action. It opens Kilix's immutable tmux-tui/tmux-cli
installer in a new tab. Start ▸ Programs ▸ **Tmux Manager** likewise opens a
new tab, preferring the installed manager and otherwise downloading Kilix's
pinned source closure before launch.

Form tabs rewrite only managed keys and preserve the rest of the file,
including comments. The raw `kitty.conf` tab exposes the whole file. Apply
reloads live through:

```bash
kitten @ action load_config_file
```

If remote control is unavailable, Settings falls back to `SIGUSR1` at
`$KITTY_PID`. If neither path works, it saves the file and tells the user to
reload manually.

The form tabs cover common appearance and behavior settings:

- font family and font size;
- foreground/background colors and opacity;
- cursor shape;
- tab bar style;
- scrollback and close-confirmation behavior;
- audio bell, copy-on-select, mouse-hide timing, and cursor blink timing;
- every top-bar status item and clickable pane-title button;
- the default-off **Activate full experience** desktop preference.

The full-experience preference is stored in the desktop `.state.json`; it is
not written into `kitty.conf`. Apply updates the desktop surfaces live.

Settings rewrites only a key that the user changed. If a key is already present
more than once, the last occurrence is treated as the active one, matching
Kitty's normal semantics. If a managed key is missing, Settings appends it under
a small Kilix desktop marker block instead of rearranging the file.

The raw `kitty.conf` tab is intentionally available for settings not modeled by
the form. Switching away from that tab preserves raw edits in the in-memory
buffer; pressing Apply or OK writes them.

Failure modes should be user-visible:

- inability to read the config opens an empty buffer rather than crashing;
- inability to write shows an error dialog;
- reload failure leaves the saved file in place and gives a manual reload hint.
