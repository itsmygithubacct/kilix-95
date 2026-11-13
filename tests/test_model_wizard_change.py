"""Change choices: saved answers can be changed from the desktop window."""
from concurrent.futures import Future
import io
import json
import sys
import tempfile
import time
from unittest.mock import Mock, patch
import harness as H
import model_discovery
import model_wizard as backend
from apps.modelwizard import open_window

ASSETS = [dict(id=name, label=name, provider='test', download_bytes=10000000,
               installed_bytes=20000000, temporary_bytes=30000000)
          for name in ('yolox_s', 'yolox_nano', 'encodec-24khz-stateful', 'encodec-48khz-frame',
                       'bonsai-image-4b-ternary-gemlite', 'bonsai-image-4b-binary-gemlite')]
requests = []


def discovery_fixture(include_answered=False):
    requests.append(include_answered)
    future = Future()
    future.set_result(backend.pages(include_answered, ensure_sizer=False, measure=False))
    future.close = lambda: None
    return future


def loaded(window):
    deadline = time.monotonic() + 3
    while window.future is not None and time.monotonic() < deadline:
        window.refresh(0)
        time.sleep(.01)
    assert window.future is None


with H.desktop_dir(), patch.object(backend, 'catalog', return_value=ASSETS), \
        patch('apps.modelwizard.Discovery', side_effect=discovery_fixture):
    # A saved choice that keeps failing (an upgraded machine's local LLM) could
    # not be changed: answered pages never came back in this window.
    backend.record('vision', 'yes', ['yolox_nano'])
    backend.record('audio', 'no', [])
    backend.record('image', 'yes', ['bonsai-image-4b-ternary-gemlite'], 'planned')
    desk = H.make_desk()

    # Start-up with nothing left to answer or install still closes by itself.
    backend.record('image', 'no', [])
    window = open_window(desk, startup=True)
    loaded(window)
    assert window not in desk.wm.windows

    # From the menu, the same state stays open on the summary with the button.
    window = open_window(desk)
    loaded(window)
    assert window in desk.wm.windows and window.batch
    assert window.change_button.enabled and not window.review_button.enabled
    window.change_choices()
    loaded(window)
    assert requests[-1] is True and not window.batch
    assert [page['id'] for page in window.pages] == ['vision', 'audio', 'image']

    # The saved answer starts checked; Continue keeps it unchanged.
    assert window.page['id'] == 'vision' and window.selected == {'yolox_nano'}
    assert window.continue_button.enabled and window.accept_button.enabled
    assert window.decline_button.enabled
    window.toggle('yolox_nano', False)
    window.toggle('yolox_s', True)
    window.accept()
    assert backend.pending()['vision']['models'] == ['yolox_s']
    assert not window.accept_button.enabled and window.continue_button.enabled
    window.advance()
    assert window.page['id'] == 'audio' and window.selected == set()
    assert window.continue_button.enabled
    window.advance()
    assert window.page['id'] == 'image'
    window.advance()
    assert window.batch and window.review_button.enabled
    assert backend.answers()['audio']['answer'] == 'no'
    assert backend.answers()['image']['answer'] == 'no'

    # A running installer blocks changes, as it blocks closing the window.
    window.job = ('directory', '/missing/result.json', time.monotonic())
    window.show_batch()
    assert not window.change_button.enabled
    window.change_choices()
    assert window.batch and window.future is None
    window.job = None
    window.close()

# The discovery worker is asked for answered pages too, and passes that on.
with tempfile.TemporaryDirectory() as directory, \
        patch.object(model_discovery, 'OwnedJob') as job:
    model_discovery.Discovery(directory, include_answered=True).close()
    assert job.call_args.args[0][-2:] == ['--worker', '--all']
fixture = Mock()
fixture.pages.return_value = [{'id': 'vision'}]
with patch.dict(sys.modules, model_wizard=fixture), patch.object(sys, 'stdout', io.StringIO()) as out:
    model_discovery.discover(True)
assert fixture.pages.call_args.kwargs == {'include_answered': True, 'ensure_sizer': True}
assert json.loads(out.getvalue()) == [{'id': 'vision'}]

print('ok')
