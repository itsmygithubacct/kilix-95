# XPane: X11 apps inside Kilix 95

How XPane embeds a host X11 application in a Kilix 95 window. Moved from the [README](../README.md).

## XPane

XPane embeds a host X11 application inside a Kilix 95 window:

1. start a private Xvfb;
2. run the app on that display;
3. capture frames with ffmpeg rawvideo;
4. chroma-key the X root background;
5. inject mouse/keyboard input through XTest;
6. bridge clipboard selections back into the desktop clipboard hub.

This is dependency-heavy, but it lets skinned or graphical apps live inside
the pixel desktop rather than escaping as unmanaged host windows.

XPane windows are chromeless from the Kilix 95 point of view. The app draws its
own skin or title bar inside the captured Xvfb surface, and Kilix 95 composites
only the opaque pixels. Chroma-keyed background pixels fall through so clicks can
land on desktop icons or windows behind the app.

The app's native Xvfb size is fixed at launch. When the Kilix 95 window is
resized, the captured frame is scaled and mouse coordinates are mapped back to
the native size. This avoids restarting Xvfb/ffmpeg on every resize.

XPane also advertises a tiny EWMH-compatible surface to the private X server.
That lets many GTK/Qt title-bar minimize/maximize requests turn into Kilix 95
window operations without taking over as a full window manager.

Every XPane owns a stream supervisor. Closing the window tears down the app,
ffmpeg, Xvfb, clipboard bridge, fd hooks, and tick hooks. A startup failure
should become a dialog rather than an uncaught exception from the desktop loop.

Limitations:

- terminal/TUI apps should not be launched through XPane because private Xvfb
  has no usable TTY for them;
- GL-heavy apps may be constrained by software rendering;
- clipboard bridging carries Unicode text, PNG/JPEG images, and local file URI
  lists through the host SDK, with incremental transfers and a 64 MiB total
  data limit; other formats and cross-display drag/drop remain unsupported;
- ffmpeg/Xvfb failures close the pane or show an error instead of retrying
  indefinitely.

File Manager Copy and Cut publish the standard URI-list, GNOME copied-files,
and KDE cut-selection representations to this same clipboard. Paste accepts
local file URIs copied by another app; a later text or image copy replaces the
file selection. Failed and same-folder moves retain their pending cut items.
