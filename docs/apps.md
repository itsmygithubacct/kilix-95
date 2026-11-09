# Kilix 95 built-in apps

The windows that ship inside Kilix 95 and the file associations that open them. Moved from the [README](../README.md). The Document Reader is described in [startup-and-voice.md](startup-and-voice.md#document-reader).

## Built-In Apps

Built-in apps are `wm.Window` subclasses opened through `apps.open(desk, name)`.
The shell catches app-launch exceptions and shows an error dialog, so a broken
app should not take down the desktop.

Notable apps:

| app | purpose | notes |
|---|---|---|
| File Manager | folder browsing and file operations | opens directories, routes files through shell associations, and supports context menus |
| Notepad | plain text editing | uses the shared text area widget and file dialogs |
| WordPad | richer document editing | targets `.krt` and RTF-style content |
| Paint | bitmap editing | useful for quick pixel/image edits inside the desktop |
| Viewer | image display | opens supported image files through Pillow |
| Amp | media playback front end | pairs with the sound scheme controls and external media helpers |
| Sound Control Panel | UI sound scheme editor | saves schemes under user data, not the repo |
| Settings | Kilix/Kitty configuration editor | writes `kitty.conf` plus shared top-bar/pane-button settings and attempts live reload |
| Control Panel / Display Properties | classic settings namespace | themes, patterns, pointers, screen savers, compatibility profiles |
| My Computer | machine namespace | drives, removable media, virtual CD, and system folders |
| Network Neighborhood / Dial-Up | connection theater and launchers | SSH/local shares plus a browser hand-off; no host network mutation |
| Printers / Device Manager | host service inspection | read-only discovery plus safe virtual-printer setup |
| My Briefcase | two-folder synchronization | no deletion propagation or two-sided-conflict overwrite |
| PowerToys / Disk Defragmenter | shell conveniences and disk-map theater | configuration helpers; the disk is never modified |
| Help | two-pane guide with live links | link rows use the ordered real-browser dispatcher |
| System Manual | searchable man-page browser | scans manpath and renders selected pages as text |
| Task Manager | running-window list | can switch to windows, request close, or open Run |
| Recycle Bin | deleted-file browser | restores or purges files from the recycle backing store |
| Find Files | bounded desktop file search | walks in chunks from a tick hook so large trees do not block the UI |
| XPane | X11-app embedding | used by external graphical apps that should stay inside the desktop |

File associations live in `shell.py`. Important routes include directories to
File Manager, text files to Notepad, `.krt`/RTF files to WordPad, images to
Viewer, audio files to Amp, `.desktop` files to launcher handling, `.vbox` files
to VirtualBox handling, and executables through a Run/Edit prompt.
