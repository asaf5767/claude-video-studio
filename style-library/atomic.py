"""Atomic local file writes: temp file in the same directory, fsync, then os.replace.

Shared by library.py and review_actions.py. Lives on its own so both can import
it without a circular dependency (review_actions.py already imports from library.py).
"""
import os
import stat
import tempfile


def atomic_write(path, data):
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    fd, temp = tempfile.mkstemp(prefix='.studio-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
