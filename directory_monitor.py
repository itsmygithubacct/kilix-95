"""Watch displayed folders; scan off-thread and commit views on the UI thread."""
import ctypes
import os
import select
import struct
import threading
import time

from directory_listing import scan

EVENT = struct.Struct('iIII')
MASK = 0x00000fce  # attrib, modify/close-write, moves, create/delete, self changes
RESET = 0x0000ec00  # self move/delete, unmount, overflow, ignored


class Inotify:
    def __init__(self, paths):
        libc = ctypes.CDLL(None, use_errno=True)
        init, add = libc.inotify_init1, libc.inotify_add_watch
        init.argtypes, init.restype = [ctypes.c_int], ctypes.c_int
        add.argtypes, add.restype = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32], ctypes.c_int
        self.fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'Directory monitoring unavailable')
        self.paths = {}
        for path in paths | {os.path.dirname(p) for p in paths}:
            wd = add(self.fd, os.fsencode(path), MASK | 0x01000000)  # IN_ONLYDIR
            if wd >= 0:
                self.paths.setdefault(wd, set()).add(path)

    def changes(self, targets):
        changed, reset = set(), False
        data = os.read(self.fd, 65536)
        offset = 0
        while offset + EVENT.size <= len(data):
            wd, mask, cookie, size = EVENT.unpack_from(data, offset)
            start = offset + EVENT.size
            if start + size > len(data):
                return set(targets), True
            name = os.fsdecode(data[start:start+size].split(bytes([0]), 1)[0])
            offset = start + size
            if mask & 0x4000:  # IN_Q_OVERFLOW: rebuild from authoritative snapshots.
                changed.update(targets)
            if mask & RESET:
                reset = True
            for path in self.paths.get(wd, ()):
                if path in targets:
                    changed.add(path)
                for target in targets:
                    if os.path.dirname(target) == path and (not name or os.path.basename(target) == name):
                        changed.add(target)
                        reset = True  # Replacement/deletion: follow the path's current inode.
        return changed, reset

    def close(self):
        os.close(self.fd)


class DirectoryMonitor:
    """One event thread and two bounded daemon scanners for all open views.

    Epochs discard results superseded by filesystem events or navigation.
    Periodic scans repair lost/unsupported notifications and rearm replaced
    directories. Slow filesystems cannot hold the desktop's input loop.
    """
    def __init__(self, desk, scanner=scan, interval=5):
        self.desk, self.scanner, self.interval = desk, scanner, interval
        self.condition = threading.Condition()
        self.closed = False
        self.targets = self.view_paths()
        self.generations, self.deadlines, self.first_dirty = {}, {}, {}
        self.busy, self.results = set(), {}
        self.serial = 0
        self.notify_r, self.notify_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self.command_r, self.command_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        desk.add_fd(self.notify_r, self.read)
        desk.tick_hooks.append(self.tick)
        self.threads = [threading.Thread(target=self.events, name='kilix95-directory-events', daemon=True)]
        self.threads += [threading.Thread(target=self.work, name='kilix95-directory-scan', daemon=True) for unused in range(2)]
        for thread in self.threads:
            thread.start()

    def view_paths(self):
        return {os.path.abspath(self.desk.shell.dir)} | {
            os.path.abspath(win.path) for win in self.desk.wm.windows
            if getattr(win, 'is_file_window', False) and hasattr(win, 'path')}

    @staticmethod
    def drain(fd):
        try: os.read(fd, 65536)
        except BlockingIOError: pass

    @staticmethod
    def signal(fd):
        try: os.write(fd, b'x')
        except BlockingIOError: pass

    def read(self):
        self.drain(self.notify_r)  # Models change in tick, after queued input.

    def dirty(self, paths, periodic=False):
        now = time.monotonic()
        with self.condition:
            if self.closed:
                return
            for path in paths & self.targets:
                if periodic and (path in self.busy or path in self.deadlines):
                    continue
                self.serial += 1
                self.generations[path] = self.serial
                first = self.first_dirty.setdefault(path, now)
                self.deadlines[path] = min(now + .12, first + .5)
                self.results.pop(path, None)
            self.condition.notify_all()

    def events(self):
        backend, known, next_scan = None, None, 0
        try:
            while True:
                with self.condition:
                    if self.closed:
                        return
                    targets = set(self.targets)
                now = time.monotonic()
                if targets != known or now >= next_scan:
                    if backend is not None:
                        backend.close(); backend = None
                    try: backend = Inotify(targets)
                    except (AttributeError, OSError): pass
                    self.dirty(targets, periodic=targets == known)
                    known = targets
                    next_scan = now + self.interval
                fds = [self.command_r] + ([backend.fd] if backend is not None else [])
                ready, unused, unused = select.select(fds, [], [], min(.25, max(0, next_scan-time.monotonic())))
                if self.command_r in ready:
                    with self.condition:
                        if self.closed:
                            return
                        self.drain(self.command_r)
                if backend is not None and backend.fd in ready:
                    changed, reset = backend.changes(targets)
                    self.dirty(changed)
                    if reset:
                        known = None
        except (OSError, ValueError):
            # Closing owned pipes wakes this thread; scanners cannot mutate UI.
            return
        finally:
            if backend is not None:
                backend.close()

    def work(self):
        while True:
            with self.condition:
                while True:
                    if self.closed:
                        return
                    eligible = {p: due for p, due in self.deadlines.items() if p not in self.busy}
                    now = time.monotonic()
                    path = min(eligible, key=eligible.get) if eligible else None
                    if path is not None and eligible[path] <= now:
                        epoch = self.generations[path]
                        self.deadlines.pop(path); self.first_dirty.pop(path, None)
                        self.busy.add(path)
                        break
                    self.condition.wait(max(.001, eligible[path]-now) if path is not None else None)
            listing = self.scanner(path)
            with self.condition:
                self.busy.discard(path)
                if not self.closed and path in self.targets and self.generations.get(path) == epoch:
                    self.results[path] = (epoch, listing)
                    self.signal(self.notify_w)
                self.condition.notify_all()

    def tick(self, now):
        targets = self.view_paths()
        with self.condition:
            if self.closed:
                return
            if targets != self.targets:
                for path in targets ^ self.targets:
                    self.serial += 1
                    self.generations[path] = self.serial
                self.targets = targets
                for path in set(self.deadlines)-targets:
                    self.deadlines.pop(path, None); self.first_dirty.pop(path, None)
                for path in set(self.results)-targets:
                    self.results.pop(path, None)
                self.signal(self.command_w)
            # Keep rows stable through menus, drags, and double-clicks.
            click = getattr(self.desk, '_last_click', (0,))[0]
            if self.desk.menus.active or self.desk.mouse_owner is not None or 0 <= time.time()-click < .45:
                return
            ready, self.results = self.results, {}
        for path, (epoch, listing) in ready.items():
            with self.condition:
                if path not in self.targets or self.generations.get(path) != epoch:
                    continue
            if path == os.path.abspath(self.desk.shell.dir):
                self.desk.shell.refresh(listing)
            for win in list(self.desk.wm.windows):
                if getattr(win, 'is_file_window', False) and os.path.abspath(win.path) == path:
                    win.refresh(listing)

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closed = True
            self.condition.notify_all()
            self.desk.remove_fd(self.notify_r)
            if self.tick in self.desk.tick_hooks:
                self.desk.tick_hooks.remove(self.tick)
            for fd in (self.notify_r, self.notify_w, self.command_r, self.command_w):
                os.close(fd)
