"""Cross-process, reentrant locks for cooperating file writers.

Lock files persist so a waiting process always locks the same inode.
The operating system releases the lock when a process exits.
"""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import os
import threading
import time

_guard = threading.Lock()
_locks = {}
_local = threading.local()


@contextmanager
def file_lock(path):
    key = str(Path(path).resolve())
    with _guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        held = getattr(_local, "held", {})
        if key in held:
            yield
            return
        target = Path(key + ".lock")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a+b") as stream:
            stream.seek(0, 2)
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 15
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"等待文件写入超时：{Path(key).name}")
                    time.sleep(0.02)
            held[key] = True
            _local.held = held
            try:
                yield
            finally:
                held.pop(key)
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def locked(path_of):
    """Lock the destination across the decorated read/modify/write operation."""
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with file_lock(path_of(*args, **kwargs)):
                return function(*args, **kwargs)
        return call
    return decorate
