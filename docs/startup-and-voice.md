# Kilix 95 startup offers, system voice and Document Reader

The windows Kilix 95 offers on Plebian-OS at startup (Kilix Workflows, system voice, model setup) and the Document Reader. Moved from the [README](../README.md).

Note on the current code (VERSION 0.2.3): every desktop start runs
`kilix wizard install-default-voice` and waits for it, in its own session with
no terminal and its output in the desktop's private `default-voice.log`. It
installs and selects the `kilix-female-02` voice without asking and without
turning the greeting on.
The **Enable system voice** window greets with `kilix-female-02`. The System
voice section below was written before that change and still names the earlier
voice as the one the offer downloads; that earlier voice remains the explicit
read-aloud opt-in in the Document Reader.

## Kilix Workflows

On Plebian-OS, Kilix 95 asks at startup whether to enable Kilix Workflows.
They use local language models only for tasks that need them; grammar and
direct actions remain usable without model downloads. The visible setup reuses
verified model files already on the computer and shows each licence before
fetching a missing model. After you opt in, Kilix checks the models at each
desktop start and brings up the same setup and licence screen if one is
missing. Updates do not reset your choice.

Choose **Enable Kilix Workflows** to start setup. A failed or interrupted setup
can be retried from the same window. **Later** leaves the question open for a
future launch, and **No thanks** declines it. Reopen setup from **Start →
Programs → Kilix Workflows…** or **Start → Settings → Kilix Workflows…**.
When workflows are enabled, the window offers **Check models** and **Turn
off**. Existing files that fail verification are left unchanged and reported
for attention; this setup does not replace a damaged or mismatched selection.

## System voice

On Plebian-OS, the first Kilix 95 launch offers **Enable system voice** in a
window. Opting in opens the pinned Piper Kristin download notice; the desktop
records the preference only after setup succeeds. A later desktop launch loads
Piper in the background and says **hello** once. The provider stays warm during
the desktop session. Startup does not block the desktop or download model weights.

Use **Settings → Voice → System voice…** (or **Start → Programs → System Voice**)
to edit the startup message or turn the feature off. An empty message preloads
Piper silently. Closing the first-launch offer leaves voice disabled. Preferences
are per-user native desktop state and survive reboots and updates. A failed setup
can be retried from the same window. `KILIX_SYSTEM_VOICE_OFFER=1` enables the offer
outside Plebian-OS; `0` suppresses the offer without disabling a saved preference.

While enabled, system voice also announces overheating, low/critical battery,
loss of a previously connected physical network link, and sustained heavy
swapping. Warnings play once per incident using clips prepared at startup.
Temperature alerts use sensor Celsius values independently of display units.
See the host SDK system-health documentation for thresholds and recovery rules.

With system voice enabled, normal machine shutdown says **Goodbye** using a
clip cached at startup. Plebian-OS listens for logind's shutdown notification and
holds a delay inhibitor only until playback finishes (bounded by logind's delay
limit). The desktop's Shut Down action also requests the clip before power-off;
the two paths suppress duplicate speech. Turning voice off, leaving the desktop,
or restarting just the desktop stays silent. Forced shutdown or power loss
cannot guarantee speech.

System voice also announces **power connected** / **running on battery** after
a power-source change stays stable for four seconds. The initial power source
is silent. **Disk space low** watches the writable local filesystems used by
`/`, home and Kilix data; it warns below 5% available when less than 2 GiB remains.
A successful Plebian-OS whole-stack update run by the desktop user announces
**update complete. restart required** when automatic restart was not requested.
Failed updates and old notices at desktop startup are silent.

## Document Reader

Open **Start → Programs → Document Reader** for local TXT, Markdown or PDF
files. Open a file, then press **Play**. The window shows the current passage
and progress, with Pause/Resume, Stop, Previous and Next controls. Resume repeats
the paused passage; Stop returns to the beginning. Closing the window stops its
own playback. The voice daemon does not need to be running.

**Use Kristin for read-aloud…** is an explicit opt-in: confirm the choice, then
complete the first-use download notice in its terminal. Only successful setup
changes the shared read-aloud default to Piper Kristin. The startup/system voice
remains a separate preference. Use **Voice settings…** to change the voice later.

Markdown is read as prose, with fenced code and formatting skipped. PDF reading
uses `pdftotext` from `poppler-utils` (included by Plebian-OS); scanned pages
need OCR first. Documents are limited to 16 MiB, with up to 8 MiB of UTF-8 text.
Long documents are read passage by passage without the terminal-pane text limit.
Desktop TXT/MD/PDF file icons also have a **Read aloud…** context action.

## Model setup

The startup **Model setup** window shows only unanswered categories. Each page
has checkbox alternatives, a recommended/default selection where available,
and sizing information. **Accept checked** or **No thanks** saves the choice;
**Continue** advances within the same window. Reopen it from **Model Setup** in
the Programs or Settings menu. Closing it preserves prior answers.

After model selection, **Review licences and install** opens a terminal box
inside the desktop. Licence questions are grouped by licence and name all
applicable models; use **Yes** or **No**, without copying an acceptance phrase.
Declined groups are skipped. Interrupted installation remains available to
retry. The same choices are accessible through `kilix wizard` in a terminal;
`kilix wizard --all` revisits answered pages and `kilix wizard finish` resumes
the final batch. The host must provide the matching model wizard backend.
