"""Bounded media batch reader: plain multi-select or an ordinary ZIP of media.

Never extract archive paths to disk. Validate the entire archive directory before
the first side effect, then verify each decompressed file's size and signature.
"""
import re
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from werkzeug.utils import secure_filename

from .upload_disk import GuardedTemporaryFile
from .anthias import PlayerError
from .library import MAX_MEDIA, _MEDIA, _signature

MAX_FILES = 20
MAX_ZIP_ENTRIES = 60  # directory records count too
MAX_TOTAL_UNPACKED = 150 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ZIP_MEDIA_BYTES = 50 * 1024 * 1024
MAX_BATCH_BYTES = MAX_MEDIA
MAX_RATIO = 150
CHUNK = 64 * 1024


class BatchError(ValueError):
    """Unsafe batch, rejected in full before any imported item."""


def _size(stream):
    """Seekable Werkzeug upload or SpooledTemporaryFile."""
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    return size


def _safe_zip_members(archive):
    info = archive.infolist()
    if len(info) > MAX_ZIP_ENTRIES:
        raise BatchError('ZIP enthält zu viele Einträge (höchstens 60).')
    seen = set()
    total = 0
    members = []
    for member in info:
        path = member.filename
        parts = PurePosixPath(path).parts
        # ZIP uses forward slashes. Backslashes/colon/control chars are never
        # accepted: no Windows drive syntax, alt streams or ambiguous paths.
        if (not path or len(path) > 260 or path.startswith('/')
                or '\\' in path or ':' in path
                or any(ord(ch) < 32 for ch in path)
                or any(part in ('', '.', '..') for part in path.rstrip('/').split('/'))
                or not parts or any(p == '..' for p in parts)):
            raise BatchError('ZIP enthält unsichere Pfade. Keine Dateien wurden importiert.')
        folded = path.rstrip('/').casefold()
        if folded in seen:
            raise BatchError('ZIP enthält doppelte Dateipfade.')
        seen.add(folded)
        mode = member.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise BatchError('ZIP enthält Verknüpfungen oder spezielle Dateien.')
        if member.flag_bits & 0x1:
            raise BatchError('Verschlüsselte ZIP-Dateien werden nicht unterstützt.')
        if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise BatchError('ZIP-Komprimierung wird nicht unterstützt.')
        if member.is_dir():
            continue
        if member.file_size > MAX_ZIP_MEDIA_BYTES:
            raise BatchError('ZIP enthält Medien über 50 MB.')
        if member.file_size > MAX_RATIO * max(1, member.compress_size):
            raise BatchError('ZIP wurde wegen ungewöhnlich hoher Komprimierung abgelehnt.')
        total += member.file_size
        if total > MAX_TOTAL_UNPACKED:
            raise BatchError('ZIP enthält über 150 MB entpackte Daten.')
        members.append(member)
    if not members:
        raise BatchError('ZIP enthält keine Dateien.')
    if len(members) > MAX_FILES:
        raise BatchError('Höchstens 20 Medien pro Import.')
    return members


def _title_and_filename(raw_name):
    # For zip folders, use the leaf name only; it is never a filesystem path.
    basename = PurePosixPath(raw_name).name
    ext = Path(basename).suffix.lower()
    title = Path(basename).stem.strip()[:100]
    title = ''.join(c for c in title if c.isprintable()).strip()
    filename = secure_filename(basename)
    if not title or not filename:
        raise ValueError('Ungültiger Dateiname.')
    if ext not in _MEDIA:
        raise ValueError('Dateityp nicht unterstützt (PNG, JPG, WebP, MP4).')
    return title, filename, ext


def _verified_stream(source, expected_size=None, max_bytes=MAX_MEDIA):
    """Validate with bounded chunks into guarded disk storage."""
    with GuardedTemporaryFile() as output:
        amount = 0
        head = b''
        while True:
            block = source.read(CHUNK)
            if not block:
                break
            amount += len(block)
            if amount > max_bytes:
                raise ValueError('Datei zu groß (Einzelvideo max. 4 GiB, ZIP-Eintrag max. 50 MiB).')
            if len(head) < 16:
                head += block[:16 - len(head)]
            output.write(block)
        if expected_size is not None and amount != expected_size:
            raise ValueError('ZIP-Dateigröße weicht vom Verzeichnis ab.')
        if not amount:
            raise ValueError('Datei ist leer.')
        yield output, head
        # Caller uses output only while generator is still active.


@contextmanager
def checked_media(source, name, expected_size=None, max_bytes=MAX_MEDIA):
    title, filename, ext = _title_and_filename(name)
    generator = _verified_stream(source, expected_size, max_bytes)
    try:
        stream, head = next(generator)
        if not _signature(head, ext):
            raise ValueError('Dateisignatur passt nicht zur Dateiendung.')
        stream.seek(0)
        yield title, filename, ext, stream
    finally:
        generator.close()


@contextmanager
def checked_direct_media(source, name):
    """A Werkzeug upload is already seekable and disk-spooled.

    Reusing it avoids a SECOND 600-MB temporary file for a direct upload.
    ZIP entries still need bounded decompression to a separate safe stream.
    """
    title, filename, ext = _title_and_filename(name)
    amount = _size(source)
    if not 0 < amount <= MAX_MEDIA:
        raise ValueError('Medium ist leer oder größer als 4 GiB')
    head = source.read(16)
    source.seek(0)
    if not _signature(head, ext):
        raise ValueError('Dateisignatur passt nicht zur Dateiendung.')
    yield title, filename, ext, source


def execute_batch(uploads, *, duration, destination, on_media):
    """Return a per-file report, not an all-or-nothing success claim.

    destination is 'player' or 'library'. on_media(title, filename, ext, stream,
    seconds) must perform exactly one append. Side effects may be irreversible.
    """
    if destination not in ('player', 'library'):
        raise BatchError('Unbekanntes Importziel.')
    if not uploads or any(not item.filename for item in uploads):
        raise BatchError('Bitte Medien oder ein ZIP auswählen.')
    if len(uploads) > MAX_FILES:
        raise BatchError('Höchstens 20 Dateien pro Upload.')
    try:
        seconds = int(duration)
    except (TypeError, ValueError):
        raise BatchError('Bilddauer muss eine ganze Zahl sein.') from None
    if not 5 <= seconds <= 3600:
        raise BatchError('Bilddauer muss zwischen 5 und 3600 Sekunden liegen.')

    from_zip = len(uploads) == 1 and uploads[0].filename.lower().endswith('.zip')
    if not from_zip and any(f.filename.lower().endswith('.zip') for f in uploads):
        raise BatchError('Eine ZIP bitte allein auswählen; keine gemischten Dateien.')
    if from_zip:
        if _size(uploads[0].stream) > MAX_ARCHIVE_BYTES:
            raise BatchError('ZIP-Datei zu groß (max. 50 MB).')
        try:
            archive = zipfile.ZipFile(uploads[0].stream)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
            raise BatchError('ZIP-Datei ist ungültig oder beschädigt.') from None
        with archive:
            members = _safe_zip_members(archive)  # zero player/library writes so far
            def process():
                for info in members:
                    name = info.filename
                    try:
                        with archive.open(info) as reader:
                            with checked_media(reader, name, info.file_size, MAX_ZIP_MEDIA_BYTES) as media:
                                on_media(*media[:3], media[3], 0 if media[2] == '.mp4' else seconds)
                        yield {'name': name, 'status': 'imported', 'message': 'Importiert'}
                    except (ValueError, OSError, EOFError, RuntimeError, zipfile.BadZipFile, PlayerError) as exc:
                        yield {'name': name, 'status': 'failed', 'message': str(exc)[:220]}
            entries = list(process())
    else:
        if sum(_size(item.stream) for item in uploads) > MAX_BATCH_BYTES:
            raise BatchError('Maximal 4 GiB je direktem Mehrfach-HTTP-Request (Browser sendet Dateien einzeln).')
        entries = []
        for item in uploads:
            name = item.filename
            try:
                with checked_direct_media(item.stream, name) as media:
                    on_media(*media[:3], media[3], 0 if media[2] == '.mp4' else seconds)
                entries.append({'name': name, 'status': 'imported', 'message': 'Importiert'})
            except (ValueError, OSError, EOFError, RuntimeError, PlayerError) as exc:
                entries.append({'name': name, 'status': 'failed', 'message': str(exc)[:220]})

    counts = {'imported': 0, 'failed': 0}
    for entry in entries:
        counts[entry['status']] += 1
    return {'ok': counts['failed'] == 0, 'partial': counts['failed'] > 0,
            'imported': counts['imported'], 'failed': counts['failed'],
            'results': entries, 'destination': destination,
            'message': f"{counts['imported']} importiert, {counts['failed']} fehlgeschlagen."}
