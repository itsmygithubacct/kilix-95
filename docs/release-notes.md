# Kilix 95 release notes

Release history of the Kilix 95 desktop provider, newest first. Moved from the [README](../README.md); the text is unchanged. Release tags for this repository are created by the coordinated Plebian-OS release procedure.

## 0.2.2.1 maintenance candidate

Model Setup removes submitted administrator passwords from terminal output before displaying or saving the diagnostic transcript, including echoes split across reads.

This source is a release candidate; installation-media and upgrade acceptance are pending.

## Release 0.2.2 — Linux

Kilix-95 0.2.2 ships in the coordinated Plebian-OS Linux release published
November 3, 2026. The `v0.2.2` tag identifies the released source; this branch
can contain later development. Use the [release's OS upgrade policy](https://github.com/itsmygithubacct/plebian-os/blob/v0.2.2/UPGRADING.md)
for supported release paths.

The optional-software model wizard now attaches a controlling terminal when
it invokes an administrator installer, so `sudo` can prompt for a password.
Optional software, model weights, and licence receipts remain separate choices.

Linux installation and lifecycle qualification covers QEMU/KVM BIOS and EFI
virtual machines. Bare-metal USB installation and physical GPU operation were
not qualified. Windows remains at `windows-v0.2.2-preview.4`; ARM64 is not a
supported OS release target. See the [published release notes](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.2.2)
for known issues and deferred feature qualification.

The PTY session manager uses the matching host's structured session interface
and cleans up its owned helper processes when the window closes. The desktop
SDK mirrors this provider with declared storage and provider adaptations;
its [manifest](https://github.com/itsmygithubacct/kilix-desktop-sdk/blob/main/manifest.toml)
records the exact standalone source revision and adaptation paths.

The RC5 desktop-completion candidate gives XPane applications their own
singleton bus and uses the matching Kilix SDK's portal relay to reach physical
desktop services. Portal request/session handles and Unix file descriptors
cross that relay while the application's windows stay on its private display.
With the matching Kilix/Pleb candidates, each local XPane is offered separately
in the physical capture picker, under its desktop application title. Capture
includes that pane's private application windows and dialogs; consent and
Stop sharing stay on the physical desktop.

- CI pairs this provider with the coordinated host's floating Start and status
  widget menus. The host's dropdowns appear above the desktop pane.
- Settings exposes the page-strip edge. Desktop Amp and sibling TUI launches
  carry the selected content installation root.
- Desktop and file-manager icons support arrow keys, Home/End, Shift selection
  ranges and Enter activation. File-manager navigation reveals offscreen rows.
- The shared clipboard hub tracks pending copies so the matching SDK can hold
  paste requests until the complete requested format arrives. Completed formats
  are usable while other representations are still being collected; the hub
  retains its previous bundle until the new bundle finishes. Failed copies refuse
  waiting pastes; expired or closed requests release their resources.
  Pending-copy notifications refresh the private panes' cached clipboard formats.
- Desktop and open file-manager views follow external file creation, removal,
  renaming and launcher edits. Filesystem scans run off the UI thread; unchanged
  items retain their accessible identities, selection and keyboard anchors.
  Refresh preserves address drafts and scroll position, defers through menus
  and drags, and refuses activation of a replaced file. Missing folders show an
  accessible status and recover when recreated. Linux directory notifications
  are backed by periodic consistency scans; owned monitors close with the desktop.
- The candidate exposes the live pixel shell through AT-SPI: desktop icons,
  windows, taskbar actions, menus, buttons, checkboxes, text editors, lists,
  tab strips and dropdowns. Requests run on the UI thread against current
  controls; closed or replaced items are refused, modal dialogs restrict
  underlying actions, and password text crosses the bridge only as bullets.
  The owned GIO helper exits with its desktop. Tab strips and dropdowns also
  support keyboard navigation and show focus. The matching native candidate
  supplies pane geometry through a bounded background observer. Component
  screen bounds and hit-testing use that live X11 placement and refuse expired,
  hidden or mismatched grids. Text character/range extents and point-to-offset
  queries run against the actual text widget on the UI thread, sharing its
  drawing origins, font and scroll positions. Character boxes include glyph
  overhang; point queries respect the text viewport. Masked fields measure only
  displayed bullets. Typed replies revalidate text, font, layout and native
  placement before returning coordinates. Broader text/coordinate qualification,
  native Kilix chrome semantics, keyboard/input workflows and complete installed
  screen-reader acceptance remain pending. Owned VM
  checks cover live icon/document/menu/dialog actions, saving edited Unicode
  text, and Orca speaking icons, menus and a real editor line. List-selection
  requests carry the selected item's identity so a refresh cannot redirect
  a pending index-based request to a replacement file.
- The text editor supports Ctrl+Home/End for document boundaries, including
  Shift selection. Accessible focus dismisses open popup menus before moving
  to a desktop icon or window control.
- Full graphics placements recur even while damage updates are active, so a
  recovered frontend can rebuild the desktop image without a manual resize.
- With the matching host candidate, a surviving broker-backed desktop refreshes
  its authenticated route from the live attach process before launching tabs.

### Firekitten desktop and quiet session audio

The startup wizard begins with the regular Plebian-OS wallpaper and offers an
optional dark twilight firekitten scene. The choice is saved before model setup
continues. Keeping the regular wallpaper leaves sampling and animation off;
Later leaves the offer unanswered. Existing custom backgrounds are preserved
until a wallpaper is explicitly chosen. The bundled regular artwork is the
Plebian-OS desktop asset, unchanged.

In the optional scene, a small optimizer sits on the back-left hill with a slow,
anchored crank cycle.
Display Properties → Background offers the optional paperclip scene, animation
on/off, and 1/5/10/30-minute sampling (five minutes by default). A one-second local
CPU sample selects scenes at 0, 5, 10, 20, 30, 60, 90 and 100 percent busy time,
normalized across logical cores. At 90–99% Kilix sits on the piles; at 100% only
one arm emerges. Sampling and animation pause when the desktop pane is unfocused
or its screen saver is active. Missed samples do not accumulate. Unsupported or
unavailable counters leave the last scene in place.

The optimizer glows and steams when swap occupancy reaches half of configured
swap with at least 256 MiB in use, or current swap traffic reaches 8 MiB/s. This
is a decorative load indicator, not a temperature measurement. The private
`paperclips_enabled`, `paperclips_animate` and `paperclips_interval` choices live
in the existing Kilix 95 shell state. Custom wallpapers are preserved; enabling
the paperclip checkbox selects the bundled firekitten scene.

System Voice offers a separate announcement volume from 0–20%, defaulting to 20%,
including greetings, power/health messages and goodbye. It requires the matching
voice runtime with `--system-volume`. Startup and shutdown songs, including custom
bindings and their Sound Properties previews, are capped at 20% of source level.
The master mixer is unchanged. Playback requires a backend with per-stream gain
(`paplay`, `ffplay`, `play`, `mpv` or VLC); bare `aplay` is not used because it
cannot honor the level.

## Release 0.2.0

Prepared for the coordinated Plebian-OS 0.2.0 release.

- A clean tap of either Super key toggles the Start menu. Key combinations,
  repeats, pointer actions, modal windows, and Alt-Tab disarm the gesture so
  ordinary desktop input is not mistaken for a Start-menu request.
- Interrupting startup now restores the terminal even before the main loop is
  active. Terminal-mode and private-frame cleanup are idempotent across both
  early exits and normal shutdown.
- The provider contract advances to Kilix SDK 1.16 for the coordinated host
  pairing while retaining the existing provider API and security declarations.

## Release 0.1.9

Published 2026-08-14 as part of the coordinated
[Plebian-OS 0.1.9 release](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.1.9).
This repository's public `v0.1.9` tag identifies the desktop-provider component
selected by that release.

- **Kilix Applications** is generated from every application in the host's
  shared catalog. Terminal-native tools open in `xterm` PTYs inside XPane, so
  File Manager, System Center, Settings, Software Center, Session Center,
  Voice Studio, Notepad, Character Map, and later catalog additions behave as
  movable Kilix 95 windows without provider-local pins. SDK 1.13 supplies
  named actions, input types, and lifecycle policy; single-instance apps are
  refocused instead of duplicated.
- **PDF Viewer** opens PDF files through the catalog's terminal-native viewer.
  The Start-menu row opens a filtered file chooser, and `.pdf` files from the
  desktop or File Manager use the viewer's fixed `open` action. PDF Conversion
  remains available in the generated application submenu for Markdown work.
- Region Painter, Cameras, and model installation are reachable from Programs
  and shared settings without private source pins or duplicate installers.
  Dictation and read-aloud settings can install the exact speech-model closure
  before reopening their diagnostic views.
- Settings exposes the completed CPU/RAM pane-chip policy. One-minute load is
  shown left of the shared chip above `1.0` by default; pane process-tree RAM
  remains on its right. Each side independently supports `auto`, `always`, and
  `off`.

## Release 0.1.8

Prepared 2026-08-07 and published 2026-08-09 as part of the coordinated
[Plebian-OS 0.1.8 release](https://github.com/itsmygithubacct/plebian-os/releases/tag/v0.1.8).

Upgrades from 0.1.7.

- Programs gains **Install Software** and a **Coding Agents** entry. The
  original text of this item is kept in the README under
  [Install Software and Coding Agents](../README.md#install-software-and-coding-agents).
- Programs also gains **Default Desktop**, which writes through
  `kilix default-desktop` — the launcher's single writer — with a context menu
  naming each desktop directly. Starting another desktop for one session was
  already possible; nothing made it the one the next login would use.
- An opened Start-menu submenu now stays open once the pointer leaves the row
  that opened it. It closes on a click outside every menu, or when another
  cascade entry replaces it; hovering an ordinary entry only moves the
  highlight. Reaching a submenu entry used to mean tracing the parent row
  exactly and crossing over without drifting onto any of the plain entries in
  between.
- Adopts the host's game verb and shared application scanner (SDK 1.8).
  `games.py` delegates install-and-boot to `kilix games play <id>`, so every
  desktop boots the same build from the same place; the handoff is probed
  rather than assumed, so a host that predates the verb keeps working and an
  offline machine with a local install loses nothing. The freedesktop scanner
  moves to `kilix_sdk.xdgapps` and `xdgapps.py` keeps only the desktop-side
  half — icons, launch modes, the VirtualBox special case.
### Fixed by the 0.1.7 review

- **A Start-menu launch could leave a dead tab.** The terminal spawns a tab's
  child from its own environment, whose `PATH` does not reliably include
  `~/.local/bin`, so a bare command name it could not resolve died before its
  first prompt and left a tab whose only trace was a resize warning — the
  0.1.7 review's dead `rollout-resume` tab. `_tab`, the choke point every
  Start-menu launcher goes through, now resolves its program where the menu
  was built (`PATH`, then `~/.local/bin`) and hands the terminal an absolute
  path. A name found in neither place gets a message box naming both.

## Release 0.1.7

Release date: 2026-08-02.

- Make `python3 main.py --version` and `--help` available before the Kilix
  native state library is built. Runtime desktop and screenshot paths retain
  the same fail-closed library check before UI setup.
- Name the Start-menu speech entries as settings/diagnostic tools and add a
  Voice Help entry that explains how to use Kilix's real page-strip controls
  in a terminal pane. Kilix 95 is a pixel framebuffer, so it cannot itself be
  a read-aloud or dictation text target. On an installed release, if needed,
  the settings entries install the exact voice runtime pinned by the active
  Kilix checkout before opening.

Version 0.1.7 is the coordinated stack release covering everything since 0.1.2,
shared with [Kilix](https://github.com/itsmygithubacct/kilix),
[Pleb](https://github.com/itsmygithubacct/pleb), and
[Plebian-OS](https://github.com/itsmygithubacct/plebian-os). It adds the pane
memory controls and monitor launcher, the Tmux Manager and PTY Sessions Start
menu entries, a **Kilix TUI** launcher, and Kilix Temps controls, on top of the
shared-SDK adoption below. Settings gains a **Session logs** tab for Kilix's
default-on pane transcripts, consuming the SDK 1.5 session-logging contract,
including the two directory budgets that bound the transcript tree: dead-pane
logs are compressed promptly, and the oldest are recompressed more densely
before any history is dropped.

Settings also gains a **Voice** tab over SDK 1.6's shared speech contract —
read-aloud and dictation engines, voice, rate, extent, devices, and a dictation
history that stays off unless it is turned on — with matching Start menu
entries. The **Tools** tab pairs the Tmux Manager with SDK 1.7's coding-agent
policy: one setting deciding whether a resumed coding agent starts with its own
approval prompts disabled, spelled out on screen because it is the one knob here
that makes an agent act without asking. This desktop now requires **Kilix SDK
1.7**. Web links now use Kilix 95's contained browser routing, which selects an
installed browser, launches it through `kilix run`, and retains the in-pane
renderer as a fallback. Release tags
for this repository are created only by the coordinated release procedure —
see Plebian-OS's
[RELEASING.md](https://github.com/itsmygithubacct/plebian-os/blob/main/RELEASING.md).
0.1.7 is the fresh-install upgrade baseline. Older installations are
reinstalled; later coordinated releases must support a preserving upgrade from
the immediately previous published release under Plebian-OS's
[upgrade policy](https://github.com/itsmygithubacct/plebian-os/blob/main/UPGRADING.md).

> The `0.1.3` and `0.1.4` sections below are **component milestones**, not
> shipped stack releases: they mark which Kilix provider SDK this desktop
> consumed. No Plebian-OS image was ever built or published for either.
> `0.1.5` was prepared as a coordinated release and never cut. `0.1.6` was an
> unpublished failed candidate; all of that work is folded into 0.1.7.

## 0.1.4 — consumes SDK 1.4

Version 0.1.4 consumes the Kilix 1.4 provider SDK and stores internal shell and
Briefcase records through `kilix_sdk.state`, backed by the host-pinned
`kilix-state-py` binding and native `kilix-state` library. Existing JSON records
are imported when a native record is absent and retained as recovery copies.

## 0.1.3 — consumes SDK 1.3

Version 0.1.3 consumes the Kilix 1.3 provider SDK: the shared immutable
content catalog drives Games, and `kilix_sdk.xapp.XAppSession` owns private X
display authentication, app/capture processes, event-driven capture fallback,
input injection, and teardown. Kilix JPAK, Kilix Rancher, and Kilix Pong arrive
through the shared catalog without separate provider-specific installers. The
shared chrome contract also exposes Kilix's volume widget in Settings.

## Release 0.1.2

Version 0.1.2 includes:

- canonical desktop source discovery under `~/.local/gpu_terminal/sources/kilix-desktops` and
  Kilix 95-owned runtime state under `~/.local/gpu_terminal/kilix-95`;
- private session frames and ephemeral installer logs, plus a fully isolated
  test environment;
- a larger classic shell with Control Panel applets, Display Properties,
  Device Manager, Network Neighborhood, Dial-Up Networking, Printers,
  My Briefcase, PowerToys, and the safe disk-map theater;
- original Plus!-style themes, additional screen savers, Quick Launch, and the
  kitten-fire wallpaper reserved for the Windows XP flavor;
- Chess Bash and Kilix Fishtank integrations plus a repaired, immutable
  Kilix-Amp install with private XDG config, data, state, and cache roots;
- a Help-menu Pleb Recovery Guide that opens the installed recovery document
  and supplies actionable `sudo` dependency repair advice when it is missing;
  and
- unique private transport files for every streamed frame, deferred retirement
  until the terminal engine has consumed them, and startup orphan reaping that
  bounds frame/cache churn and prevents delayed AMP-session `SIGBUS` crashes.

## Release 0.1.1

Version 0.1.1 declares the provider/SDK contract, preserves the default-password
security baseline across provider choices, writes settings only to XDG user
configuration, and pins optional downloaded game/app sources to immutable
commits with safe archive extraction.
