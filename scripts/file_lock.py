"""Small standard-library exclusive file locks for Windows and POSIX."""

from __future__ import annotations

import os


def lock_exclusive(file, *, nonblocking=False):
    """Lock one byte on Windows or the whole file on POSIX.

    The caller owns ``file``; closing it releases the lock on both platforms.
    """
    if os.name == "nt":
        import msvcrt

        if os.fstat(file.fileno()).st_size == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        try:
            msvcrt.locking(
                file.fileno(),
                msvcrt.LK_NBLCK if nonblocking else msvcrt.LK_LOCK,
                1,
            )
        except OSError as exc:
            if nonblocking:
                raise BlockingIOError("file is already locked") from exc
            raise
    else:
        import fcntl

        operation = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        fcntl.flock(file.fileno(), operation)
