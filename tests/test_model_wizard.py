"""One window, explicit Continue, durable skip, alternate checkboxes and retry."""
from pathlib import Path
import os
import time
from unittest.mock import patch
import harness as H
import model_wizard as backend
from apps.modelwizard import open_window

ASSETS = [dict(id=name, label=name, provider='test', download_bytes=10000000,
               installed_bytes=20000000, temporary_bytes=30000000)
          for name in ('yolox_s', 'yolox_nano', 'encodec-24khz-stateful', 'encodec-48khz-frame',
                       'bonsai-image-4b-ternary-gemlite', 'bonsai-image-4b-binary-gemlite')]


def loaded(window):
    deadline = time.monotonic() + 3
    while window.future is not None and time.monotonic() < deadline:
        window.refresh(0)
        time.sleep(.01)
    assert window.pages


with H.desktop_dir(), patch.object(backend, 'catalog', return_value=ASSETS):
    desk = H.make_desk()
    window = open_window(desk)
    loaded(window)
    assert open_window(desk) is window
    assert sum(type(w).__name__ == 'ModelWizard' for w in desk.wm.windows) == 1
    assert window.page['id'] == 'vision'
    assert window.checks[0].checked and not window.checks[1].checked
    assert not window.continue_button.enabled
    window.advance()
    assert window.page['id'] == 'vision'
    window.toggle('yolox_s', False)
    window.toggle('yolox_nano', True)
    with patch.object(desk.shell, '_tab') as tab:
        window.accept()
    tab.assert_not_called()
    assert backend.pending()['vision']['models'] == ['yolox_nano']
    assert window.continue_button.enabled and not window.accept_button.enabled
    assert window in desk.wm.windows
    window.advance()
    assert window.page['id'] == 'audio'
    assert not window.continue_button.enabled
    preview = os.environ.get('WIZARD_PREVIEW')
    if preview:
        window.render().save(preview)
    window.close()
    assert 'audio' not in backend.answers()
    window = open_window(desk)
    loaded(window)
    assert window.page['id'] == 'audio'  # declined vision is skipped after reopening
    window.decline(); window.advance()
    assert window.page['id'] == 'image'
    window.decline(); window.advance()
    assert window.batch and window in desk.wm.windows
    assert window.review_button.enabled
    with patch('apps.licenseterminal.open_window') as terminal:
        window.start_batch()
    command = terminal.call_args.args[1]
    assert 'finish' in command and '--result' in command
    result = window.job[1]
    backend.atomic_json(result, {'ok': False, 'error': 'Download failed'})
    window.refresh(0)
    assert window.review_button.enabled and backend.pending()
    window.close()
    window = open_window(desk)
    deadline = time.monotonic() + 3
    while window.future is not None and time.monotonic() < deadline:
        window.refresh(0); time.sleep(.01)
    assert window in desk.wm.windows and window.batch
    backend.record('vision', 'yes', ['yolox_nano'])
    window.refresh(0)
    assert not window.review_button.enabled
    window.close()

print('model wizard flow: OK')
