"""A helper echo must not expose passwords in memory, widgets or saved logs."""
from pathlib import Path
import sys
import termios
import time

import harness as H
from apps.licenseterminal import PasswordOutputFilter, open_window


secret = 'fixture-private-π'.encode()
for split in range(len(secret) + 1):
    output = PasswordOutputFilter()
    output.protect(secret)
    first = output.feed(b'Before: ' + secret[:split])
    if split < len(secret):
        assert first == b'Before: '
    second = output.feed(secret[split:] + b'\nAfter.\n')
    assert first + second == b'Before: [password removed]\nAfter.\n'
    assert output.feed(b'', final=True) == b''

output = PasswordOutputFilter()
output.protect(b'abc')
output.protect(b'abcdef')
assert output.feed(b'abc') == b''
assert output.feed(b'def abc!') == b'[password removed] [password removed]!'
assert output.feed(b'ab') == b''
assert output.feed(b'', final=True) == b'[password removed]'
assert output.feed(b'abcde', final=True) == b'[password removed]'
output.clear()
assert not output.secrets and not output.pending


def until(predicate, window):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        window.pump()
        window.tick(0)
        time.sleep(.01)
    assert predicate(), 'Timed out waiting for the test helper'


with H.desktop_dir() as temporary:
    desk = H.make_desk()
    log = Path(temporary) / 'transcript.log'
    # Exercise a real PTY and split the output with an explicit handshake.
    # getpass restores echo before this deliberately faulty helper prints it.
    release = Path(temporary) / 'release'
    script = f'''
import getpass, os, time
from pathlib import Path
value = getpass.getpass('Administrator password: ').encode()
os.write(1, b'Helper echo: ' + value[:8])
while not Path({str(release)!r}).exists(): time.sleep(.01)
os.write(1, value[8:] + b'\\n')
assert input('Continue? [y/N] ') == 'n'
'''
    window = open_window(desk, [sys.executable, '-c', script], log_path=log)
    try:
        until(lambda: window.password.enabled, window)
        H.type_text(desk, secret.decode())
        window.submit_password()
        until(lambda: 'Helper echo: ' in window.output, window)
        # Even the incomplete prefix must never reach any output sink.
        for text in (window.output, window.transcript.text(), log.read_text()):
            assert 'fixture-' not in text
        release.touch()
        until(lambda: window.no.enabled, window)
        window.no.cb()
        until(lambda: window.finished, window)
        assert window.process.returncode == 0
        for text in (window.output, window.transcript.text(), log.read_text()):
            assert secret.decode() not in text
            assert 'Helper echo: [password removed]' in text
    finally:
        window.close()
    assert not window.password_output.secrets and not window.password_output.pending

    # A terminal mode check and os.write are separate operations. Simulate the
    # worker restoring ECHO in between, so the kernel itself echoes the input.
    log = Path(temporary) / 'race.log'
    window = open_window(desk, [sys.executable, '-c',
        "import getpass; getpass.getpass('Administrator password: '); print('Done.')"],
        log_path=log)
    try:
        until(lambda: window.password.enabled, window)
        H.type_text(desk, 'fixture-race-secret')
        original_check = window.hidden_input
        def restore_after_check():
            hidden = original_check()
            attributes = termios.tcgetattr(window.master)
            attributes[3] |= termios.ECHO
            termios.tcsetattr(window.master, termios.TCSANOW, attributes)
            return hidden
        window.hidden_input = restore_after_check
        window.submit_password()
        window.hidden_input = original_check
        until(lambda: window.finished, window)
        assert window.process.returncode == 0
        for text in (window.output, window.transcript.text(), log.read_text()):
            assert 'fixture-race-secret' not in text
            assert '[password removed]' in text
    finally:
        window.close()

    # A short password can also occur inside the subsequent Yes/No prompt.
    window = open_window(desk, [sys.executable, '-c',
        "import getpass; getpass.getpass('Password: '); assert input('Continue? [y/N] ') == 'n'"])
    try:
        until(lambda: window.password.enabled, window)
        H.type_text(desk, 'y')
        window.submit_password()
        until(lambda: window.no.enabled, window)
        window.no.cb()
        until(lambda: window.finished, window)
        assert window.process.returncode == 0
    finally:
        window.close()
    assert window.prompt_tail == b''

print('embedded terminal echoed-password protection: OK')
