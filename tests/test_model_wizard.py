"""One window, explicit Continue, durable skip, alternate checkboxes and retry."""
from pathlib import Path
from concurrent.futures import Future
import os
import time
from unittest.mock import patch
import harness as H
import model_wizard as backend
import theme as T
import widgets as W
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


def discovery_fixture():
    # UI flow uses deterministic discovery; worker ownership is tested separately.
    future = Future()
    future.set_result(backend.pages(ensure_sizer=False, measure=False))
    future.close = lambda: None
    return future


with H.desktop_dir(), patch.object(backend, 'catalog', return_value=ASSETS), \
        patch('apps.modelwizard.Discovery', side_effect=discovery_fixture):
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
    run_directory = Path(result).parent
    error_log = str(run_directory / 'error.log')
    backend.atomic_json(result, {'ok': False, 'error': 'Download failed', 'error_log': error_log})
    window.refresh(0)
    assert run_directory.is_dir() and Path(result).is_file()
    assert terminal.call_args.kwargs['log_path'] == str(run_directory / 'transcript.log')
    assert window.log_path == error_log
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

with H.desktop_dir(), patch('apps.modelwizard.Discovery', side_effect=OSError('catalog unavailable')):
    desk = H.make_desk()
    window = open_window(desk)
    deadline = time.monotonic() + 3
    while window.future is not None and time.monotonic() < deadline:
        window.refresh(0); time.sleep(.01)
    assert 'catalog unavailable' in window.error
    assert Path(window.log_path).is_file()
    latest = backend.read_json(backend.state_root() / 'model-wizard-last-result.json')
    assert latest['phase'] == 'load model setup'
    window.close()

with H.desktop_dir(), patch('apps.modelwizard.Discovery', side_effect=OSError('worker could not start')):
    desk = H.make_desk()
    window = open_window(desk)
    # Closing before the first UI tick must still retain the startup failure;
    # its completed Future has no owned process and no close() method.
    window.close()
    assert window not in desk.wm.windows
    assert window.future is None and window.refresh not in desk.tick_hooks
    assert 'worker could not start' in Path(window.log_path).read_text()

# Real catalog notes must remain accessible before any saved choice or licence
# action. Use the normal keyboard route from checkbox to its Details button.
disclosed_ids = {'qwen3.5-4b', 'granite-vision-4.1-4b'}
disclosed = [row for row in backend.catalog() if row['id'] in disclosed_ids]
assert {row['id'] for row in disclosed} == disclosed_ids
with H.desktop_dir(), patch.object(backend, 'catalog', return_value=disclosed), \
        patch('apps.modelwizard.Discovery', side_effect=discovery_fixture), \
        patch.object(backend, 'apply') as apply:
    desk = H.make_desk()
    window = open_window(desk)
    loaded(window)
    for index, page in enumerate(window.pages):
        window.index = index
        window.selected = {page['default']} if page['default'] else set()
        window.show_page()
        row = page['models'][0]
        checkbox = window.checks[0]
        assert row['id'] in checkbox.text and '**' not in checkbox.text
        assert checkbox.x + checkbox.w < 545
        expected = 'name-inferred' if row['id'] == 'qwen3.5-4b' else 'trust_remote_code=True'
        H.key(desk, 'Tab')
        assert window.focus.text == 'Details...'
        H.key(desk, 'Enter')
        dialog = desk.wm.windows[-1]
        assert dialog.modal and dialog.title == 'Model details'
        viewer = dialog.focus
        assert isinstance(viewer, W.TextArea) and viewer.read_only
        full = ' '.join(viewer.text().split())
        assert expected in full and row['id'] in full and '**' not in full
        assert 'do not record your licence agreement' in full
        assert all(T.text_w(viewer.font, line) <= viewer.text_viewport()[2]
                   for line in viewer.lines)
        original = viewer.text()
        H.key(desk, 'x', text='x')
        assert viewer.text() == original
        H.key(desk, 'Escape')
        assert dialog not in desk.wm.windows
        assert backend.answers() == {} and not backend.pending()
        expected_download = backend.size_text(row['download_bytes'])
        assert expected_download + ' download' in window.status.text
    # A long backend advisory has no line-count cap, and End reaches its final
    # alternative using the same read-only keyboard navigation as manuals.
    note = ('No confirmed fit. ' * 35 +
            'Install and start the local Ollama backend, then retry kilix wizard finish. '
            'You can also revisit the System-local LLM page and decline it.')
    window.page['recommendation'] = note
    window.show_page()
    H.key(desk, 'Tab', shift=True)
    assert window.focus is window.recommendation
    H.key(desk, 'End')
    viewer = window.recommendation
    assert ' '.join(viewer.text().split()) == ' '.join(note.split())
    visible = ' '.join(viewer.lines[viewer.sb.pos:viewer.sb.pos + viewer._rows()])
    assert 'System-local LLM page and decline it.' in visible
    assert viewer.sb.pos > 0
    apply.assert_not_called()
    window.close()

print('model wizard flow: OK')
