"""The embedded player requests a catalog profile and only a successful terminal resumes it."""
import os
from pathlib import Path
import socket
from unittest.mock import patch

import harness as H
from apps.amp_model_setup import AmpModelSetup

with H.desktop_dir() as temporary:
    desk = H.make_desk()
    store = Path(temporary) / 'unused-model-store'
    long_tmp = Path(temporary) / ('t' * 95)
    long_tmp.mkdir()
    with patch('tempfile.tempdir', str(long_tmp)):
        host = AmpModelSetup(desk, str(store))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as player:
            player.bind('')
            player.connect(host.path)
            player.settimeout(1)
            with patch('apps.licenseterminal.open_window') as launch, \
                    patch('wizard_converters.encodec_transfer', return_value=(['missing'], 239108136)):
                player.send(bytes([2]))
                host.receive()
                dialog = desk.wm.active
                assert '48 kHz stereo' in dialog.widgets[0].text
                assert '228.0 MiB' in dialog.widgets[0].text
                assert not store.exists()
                other = AmpModelSetup(desk, str(store))
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as second:
                        second.bind('')
                        second.settimeout(1)
                        second.sendto(bytes([2]), other.path)
                        other.receive()
                        assert second.recv(2) == bytes([0]) and desk.wm.active is dialog
                finally:
                    other.close()
                dialog.request_close()
                assert player.recv(2) == bytes([0])
                launch.assert_not_called()
                for accept, expected in [(False, 0), (True, 1)]:
                    player.send(bytes([1]))
                    host.receive()
                    dialog = desk.wm.active
                    button = next(item for item in dialog.widgets if getattr(item, 'text', '') == 'Set up model')
                    button.cb()
                    assert launch.call_args.args[1] == ['/usr/bin/kilix', 'models', '--root',
                                                       str(store), 'install', 'encodec-24khz-stateful']
                    launch.call_args.kwargs['on_done'](accept)
                    assert player.recv(2) == bytes([expected])
                player.send(b'unrecognized')
                host.receive()
                assert host.pending is None
    finally:
        host.close()
    assert not os.path.exists(host.path)
print('ok')
