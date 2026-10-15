"""Bounded disk-backed uploads with headroom for the single-worker deployment."""
import errno
import os
import shutil
import tempfile
import threading

from flask import Request

HUB_RESERVE_BYTES = 1024 ** 3
_write_lock = threading.Lock()


class HubStorageFull(OSError):
    def __init__(self):
        super().__init__('Zu wenig temporärer Hub-Speicher oder Speicher nicht messbar. '
                         'Mindestens 1 GiB Reserve erforderlich. Ziel vor Wiederholung prüfen.')


def validate_temp_directory():
    """An explicit TMPDIR must work; never silently fall back to RAM-backed /tmp."""
    configured = os.environ.get('TMPDIR')
    if configured:
        try:
            with tempfile.TemporaryFile(dir=configured):
                pass
            # tempfile may have cached a fallback before application startup.
            tempfile.tempdir = os.path.abspath(configured)
        except OSError as exc:
            raise RuntimeError('TMPDIR must exist and be writable; refusing fallback') from exc


def guarded_write(stream, data):
    """Serialize check/write/flush so concurrent Hub threads retain a disk floor.

    External writers and filesystem quotas are not reservations; ENOSPC/EDQUOT
    still need handling. fstatvfs via the actual descriptor checks the right FS.
    """
    with _write_lock:
        try:
            try:
                free = shutil.disk_usage(stream.fileno()).free
            except OSError as exc:
                raise HubStorageFull() from exc
            if free < len(data) + HUB_RESERVE_BYTES:
                raise HubStorageFull()
            written = stream.write(data)
            stream.flush()
            return written
        except HubStorageFull:
            raise
        except OSError as exc:
            if exc.errno in (errno.ENOSPC, errno.EDQUOT):
                raise HubStorageFull() from exc
            raise


class GuardedTemporaryFile:
    def __init__(self):
        try:
            self.stream = tempfile.TemporaryFile(mode='w+b')
        except OSError as exc:
            if exc.errno in (errno.ENOSPC, errno.EDQUOT):
                raise HubStorageFull() from exc
            raise

    def write(self, data):
        return guarded_write(self.stream, data)

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DiskRequest(Request):
    def _get_file_stream(self, total_content_length, content_type,
                         filename=None, content_length=None):
        stream = GuardedTemporaryFile()
        # Parsing may abort before Werkzeug populates request.files. Track all
        # opened streams so even a truncated/oversized/full-disk parse closes them.
        self.__dict__.setdefault('_upload_streams', []).append(stream)
        return stream

    def close(self):
        try:
            super().close()
        finally:
            for stream in self.__dict__.get('_upload_streams', []):
                stream.close()
