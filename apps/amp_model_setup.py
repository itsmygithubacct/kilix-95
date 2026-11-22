"""Handle a packaged player's first-use request in the desktop's setup terminal."""
import os
import socket
import tempfile

import wm

PROFILES = {b'\x01': ('encodec-24khz-stateful', '24 kHz mono'),
            b'\x02': ('encodec-48khz-frame', '48 kHz stereo')}


class AmpModelSetup:
    def __init__(self, desk, model_root):
        self.desk = desk
        self.model_root = model_root
        self.pending = None
        self.directory = tempfile.TemporaryDirectory(prefix='kilix-amp-')
        self.path = os.path.join(self.directory.name, 'setup')
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.socket.bind(self.path)
            self.socket.setblocking(False)
            desk.add_fd(self.socket.fileno(), self.receive)
        except BaseException:
            self.socket.close()
            self.directory.cleanup()
            raise

    def close(self):
        if self.socket.fileno() >= 0:
            self.desk.remove_fd(self.socket.fileno())
            self.socket.close()
            self.directory.cleanup()
        self.pending = None

    def reply(self, peer, success):
        if self.socket.fileno() >= 0:
            try:
                self.socket.sendto(bytes([bool(success)]), peer)
            except OSError:
                pass  # The player may have closed or moved on to another track.

    def receive(self):
        try:
            data, peer = self.socket.recvfrom(2)
        except BlockingIOError:
            return
        if data not in PROFILES or not peer:
            return
        if self.pending is not None:
            self.reply(peer, False)
            return
        self.pending = peer
        asset, label = PROFILES[data]

        def finished(success):
            if self.pending == peer:
                self.pending = None
                self.reply(peer, success)

        def answered(choice):
            if self.pending != peer:
                return
            if choice != 'Set up model':
                finished(False)
                return
            from .licenseterminal import open_window
            try:
                open_window(self.desk, ['/usr/bin/kilix', 'models', '--root', self.model_root,
                                        'install', asset], on_done=finished)
            except (OSError, RuntimeError) as error:
                finished(False)
                wm.msgbox(self.desk, 'EnCodec model setup', str(error), icon='error')

        import content_models
        from model_wizard import model_download_bytes, size_text
        from wizard_converters import encodec_transfer
        try:
            api = content_models._api()
            spec = content_models._verified_catalog(api).require_asset(asset)
            needed, extra = encodec_transfer(self.model_root, [spec])
            sizes = f'Model download: {size_text(model_download_bytes(spec))}.'
            if needed and extra:
                sizes += f' Shared converter: {size_text(extra)} once.'
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            finished(False)
            wm.msgbox(self.desk, 'EnCodec model setup', str(error), icon='error')
            return
        dialog = wm.msgbox(self.desk, 'EnCodec model setup',
                           f'This track needs the {label} EnCodec model. {sizes} '
                           'Review the licence in Model Setup. Playback resumes after setup.',
                           icon='amp', buttons=('Later', 'Set up model'), cb=answered)

        def dismiss():
            dialog.close()
            finished(False)

        dialog.request_close = dismiss
