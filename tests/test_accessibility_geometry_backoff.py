"""A refused pane-geometry query backs off instead of polling forever."""
import sys
import types

import harness as H          # noqa: sets up sys.path for the imports below
import accessibility


class Stop:
    def __init__(self, limit):
        self.delays, self.limit = [], limit

    def is_set(self):
        return len(self.delays) >= self.limit

    def wait(self, delay):
        self.delays.append(delay)
        return self.is_set()


def observe(answers):
    controller = object.__new__(accessibility.Controller)
    controller._geometry = None
    controller._geometry_stop = Stop(len(answers))
    replies = iter(answers)

    def current(timeout):
        answer = next(replies)
        if answer is None:
            raise RuntimeError('get-pane-geometry is not authorised')
        return answer, None

    fake = types.ModuleType('kilix_sdk.geometry')
    fake.current = current
    saved = sys.modules.get('kilix_sdk.geometry')
    sys.modules['kilix_sdk.geometry'] = fake
    try:
        controller._observe_geometry()
    finally:
        if saved is None:
            del sys.modules['kilix_sdk.geometry']
        else:
            sys.modules['kilix_sdk.geometry'] = saved
    return controller, controller._geometry_stop.delays


controller, delays = observe([None] * 10)
assert delays == [.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0, 30.0], delays
assert controller._geometry is None

controller, delays = observe([None, None, {'pane': 1}, None])
assert delays == [.5, 1.0, .25, .5], delays

print('Geometry backoff checks passed.')
