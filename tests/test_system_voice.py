"""First-run offer, opt-in setup, durable greeting and desktop ownership."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import mock
import harness as H
import system_voice as V

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_SYSTEM_VOICE_OFFER':'1'}):
    desk=H.make_desk()
    voice=V.controller(desk)
    with mock.patch.object(voice,'start') as start, \
            mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), \
            mock.patch('system_voice.subprocess.call',return_value=0) as install:
        voice.startup()
        assert H.find_window(desk,'SystemVoice')
        assert voice.state['offered'] and not voice.state['enabled']
        assert voice.state['greeting']=='hello'
        start.assert_not_called()
        install.assert_called_once()
        assert install.call_args.args[0]==['/fixture/kilix','wizard','install-default-voice']
        assert '--prepare-system-voice' not in install.call_args.args[0]
        assert '--enable-kristin' not in install.call_args.args[0]
    count=len(desk.wm.windows)
    with mock.patch('system_voice.subprocess.call',return_value=0):
        voice.startup()
    assert len(desk.wm.windows)==count
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch.object(desk.shell,'_tab',return_value=True):
        voice.enable('Hello from home')
        assert not voice.state['enabled']
        Path(voice.job[1]).write_text(json.dumps({'exit_code':3}))
        voice.tick(0)
        assert not voice.state['enabled'] and voice.job is None
        voice.enable('Hello from home')
        Path(voice.job[1]).write_text(json.dumps({'exit_code':0}))
        with mock.patch.object(voice,'start') as start:
            voice.tick(0)
            start.assert_called_once()
    assert voice.state['enabled'] and voice.state['greeting']=='Hello from home'
    # A later desktop launch reads the same durable preference and greets.
    later=V.Controller(desk)
    assert later.state['enabled'] and later.state['greeting']=='Hello from home'
    with mock.patch.object(later,'start') as start, mock.patch('system_voice.subprocess.call',return_value=0):
        later.startup()
        start.assert_called_once()
    with mock.patch.object(voice,'stop') as stop:
        voice.disable()
        stop.assert_called_once()
    assert not V.Controller(desk).state['enabled']
    voice.close();later.close()

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_SYSTEM_VOICE_OFFER':'0'}):
    desk=H.make_desk();voice=V.controller(desk)
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), \
            mock.patch('system_voice.subprocess.call',return_value=0) as install:
        voice.startup()
        install.assert_called_once()
        assert install.call_args.args[0]==['/fixture/kilix','wizard','install-default-voice']
    assert H.find_window(desk,'SystemVoice') is None
    assert not voice.state['enabled']
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch('system_voice.subprocess.Popen') as spawn:
        process=spawn.return_value;process.poll.return_value=None
        voice.state['greeting']='hello; $(false)'
        voice.start();voice.start()
        spawn.assert_called_once()
        assert spawn.call_args.args[0][-1]=='--speak=hello; $(false)'
        voice.close()
        process.stdin.close.assert_called_once()
        process.terminate.assert_called_once()
    # Persist failure must not falsely claim enablement.
    with mock.patch.object(voice.store,'save_dict',side_effect=OSError('disk full')):
        try:voice.save(enabled=True)
        except OSError:pass
        else:raise AssertionError('save error swallowed')
        assert not voice.state['enabled']
print('ok')

# Shutdown requests use the existing worker, await its acknowledgement, and
# leave it alive in case the OS refuses power-off. Never power off in tests.
with H.desktop_dir():
    desk=H.make_desk();voice=V.controller(desk)
    voice.state['enabled']=True
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch('system_voice.subprocess.Popen') as spawn:
        process=spawn.return_value;process.poll.return_value=None
        voice.start()
        def acknowledge():
            with open(voice.log.name,'ab') as log:
                log.write(b'System voice goodbye complete\n')
        process.stdin.flush.side_effect=acknowledge
        voice.goodbye()
        process.stdin.write.assert_called_once_with(b'g')
        process.terminate.assert_not_called()
        process.stdin.write.reset_mock()
        voice.state['enabled']=False
        voice.goodbye()
        process.stdin.write.assert_not_called()
        voice.state['enabled']=True
        process.stdin.flush.side_effect=None
        with mock.patch('system_voice.time.monotonic',side_effect=[0,1,5]), mock.patch('system_voice.time.sleep'):
            voice.goodbye()  # No acknowledgement: bounded wait, then power-off can proceed.
        process.stdin.write.side_effect=BrokenPipeError()
        voice.goodbye()  # failed speech cannot block shutdown
        voice.close()
    order=[]
    with mock.patch.object(voice,'goodbye',side_effect=lambda:order.append('goodbye')), mock.patch.object(desk.shell,'_spawn_kitty_launch',side_effect=lambda *a:order.append(a[1])):
        desk.shell._power_off()
    assert order==['goodbye','systemctl poweroff']

# Announcement gain is private durable state, defaults quiet, and is bounded.
with H.desktop_dir():
    desk=H.make_desk(); voice=V.controller(desk)
    assert voice.state['volume']==20
    voice.save(enabled=True)
    with mock.patch.object(voice,'start'):
        voice.enable('hello',7)
    assert V.Controller(desk).state['volume']==7
    for invalid in (-1,21,True,'10'):
        try: voice.enable('hello',invalid)
        except ValueError: pass
        else: raise AssertionError(invalid)
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch('system_voice.subprocess.Popen') as spawn:
        spawn.return_value.poll.return_value=None
        voice.start(silent=True)
        assert '--system-volume=7' in spawn.call_args.args[0]
        assert spawn.call_args.args[0][-1]=='--speak='
        voice.close()
    voice.save(volume=100)
    assert V.Controller(desk).state['volume']==20

# First run installs the default voice while the desktop owns the terminal.
# The installer's output must not be drawn over the desktop, and it must not
# read keys typed at the desktop. Run a real fixture launcher with the
# desktop's stdin, stdout and stderr replaced by a pipe holding a key press and
# a capture file, then compare what each side saw.
with H.desktop_dir() as home:
    desk=H.make_desk();voice=V.Controller(desk)
    launcher=Path(home)/'bin'/'kilix';launcher.parent.mkdir()
    launcher.write_text('#!/bin/sh\n'
                        'echo "Prepared 2 packages in 3ms"\n'
                        'echo "Installed kilix-content" >&2\n'
                        'if IFS= read -r line; then echo "read:$line"; else echo "stdin:eof"; fi\n'
                        'echo "session:$(cut -d" " -f6 /proc/$$/stat) pid:$$"\n'
                        'echo "git-prompt:${GIT_TERMINAL_PROMPT-unset}"\n')
    launcher.chmod(0o755)
    screen=tempfile.TemporaryFile()
    keys_read,keys_write=os.pipe()
    os.write(keys_write,b'desktop-key\n')
    saved=[os.dup(fd) for fd in (0,1,2)]
    try:
        os.dup2(keys_read,0);os.dup2(screen.fileno(),1);os.dup2(screen.fileno(),2)
        with mock.patch.object(desk.shell,'kilix_tts_target',return_value=[str(launcher),'tts']):
            installed=voice.install_default_voice()
    finally:
        for fd,copy in zip((0,1,2),saved):
            os.dup2(copy,fd);os.close(copy)
        os.close(keys_read);os.close(keys_write)
    screen.seek(0);drawn=screen.read();screen.close()
    assert installed is True
    assert drawn==b'',drawn
    log=Path(os.environ['KILIX95_STATE_HOME'])/V.DEFAULT_VOICE_LOG
    text=log.read_text()
    assert 'Prepared 2 packages in 3ms' in text and 'Installed kilix-content' in text,text
    assert 'stdin:eof' in text and 'desktop-key' not in text,text
    # Its own session: no controlling terminal to open /dev/tty on, and git
    # must fail a credential question instead of asking one.
    session=next(line for line in text.splitlines() if line.startswith('session:'))
    leader,pid=(part.split(':')[1] for part in session.split())
    assert leader==pid and int(leader)!=os.getsid(0),session
    assert 'git-prompt:0' in text,text
    # The log keeps the newest run only.
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=[str(launcher),'tts']), \
            mock.patch('system_voice.subprocess.call',return_value=1) as install:
        assert voice.install_default_voice() is False
        assert install.call_args.kwargs['stdin'] is subprocess.DEVNULL
    assert log.read_text()==''
    # A log that cannot be opened sends the output nowhere, not to the screen.
    log.unlink();log.mkdir()
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=[str(launcher),'tts']), \
            mock.patch('system_voice.subprocess.call',return_value=0) as install:
        assert voice.install_default_voice() is True
        kwargs=install.call_args.kwargs
        assert kwargs['stdout'] is subprocess.DEVNULL and kwargs['stderr'] is subprocess.DEVNULL,kwargs
        assert kwargs['stdin'] is subprocess.DEVNULL and kwargs['start_new_session'] is True,kwargs
    voice.close()

# A Paradee ready line is the fresh-install session. Female-02 still updates
# the status, and this does not change an already-enabled greeting.
with H.desktop_dir():
    desk=H.make_desk(); voice=V.controller(desk)
    voice.state['enabled']=True
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), \
            mock.patch('system_voice.subprocess.Popen') as spawn:
        process=spawn.return_value; process.poll.return_value=None
        voice.start()
        assert voice.status=='Loading system voice…'
        with open(voice.log.name,'ab') as log:
            log.write(b'System voice ready: paradee af_heart\n')
        voice.tick(0)
        assert voice.status=='Paradee is ready for this session.'
        voice.stop()
        voice.start()
        with open(voice.log.name,'ab') as log:
            log.write(b'System voice ready: kilix-female-02\n')
        voice.tick(0)
        assert voice.status=='kilix-female-02 is ready for this session.'
        voice.close()
