"""Conservative capacity estimate from Anthias API /api/v2/info.free_space.

Anthias reports Django filesizeformat text (e.g. "15.0\u00a0GB"), NOT exact
bytes or the total filesystem size. Never infer more available space than
reported. The margin accommodates its one-decimal rounding.
"""
import os
import re
from decimal import Decimal, InvalidOperation

GIB = 1024 ** 3
MIB = 1024 ** 2
MAX_MEDIA_BYTES = GIB                 # per media file
MAX_REQUEST_BYTES = 2 * GIB + 2 * MIB # up to 2 GiB template ZIP + form
MIN_PI_RESERVE = 2 * GIB              # absolute free-space floor
PI_RESERVE_FRACTION = Decimal('0.20') # keep a further 20% of reported free
_SPACE = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*(BYTE[S]?|B|[KMGTPE]I?B|[KMGTPE])\s*$', re.I)
_POWERS = {'B': 0, 'BYTE': 0, 'BYTES': 0, 'K': 1, 'M': 2,
           'G': 3, 'T': 4, 'P': 5, 'E': 6}


def capacity(info):
    """Return display/preflight data, or None for missing/unknown format."""
    if not isinstance(info, dict):
        return None
    raw = info.get('free_space')
    # A few legacy APIs report whole byte counts instead of formatted text.
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        free = raw
        reserve = max(MIN_PI_RESERVE, int(free * PI_RESERVE_FRACTION))
        usable = max(0, free - reserve)
        return {'reported': f'{free / GIB:.1f} GiB', 'free_bytes': free,
                'reserve_bytes': reserve, 'usable_bytes': usable,
                'usable_gib': f'{usable / GIB:.1f}',
                'reserve_gib': f'{reserve / GIB:.1f}'}
    if not isinstance(raw, str):
        return None
    match = _SPACE.fullmatch(raw.replace('\u00a0', ' ').strip())
    if not match:
        return None
    unit = match.group(2).upper()
    prefix = unit[:1] if unit not in ('B', 'BYTE', 'BYTES') else unit
    try:
        value = Decimal(match.group(1).replace(',', '.'))
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    scale = 1024 ** _POWERS[prefix]
    # A one-decimal Anthias value may round UP by half of its last shown digit.
    # Subtract that possible discrepancy from the advertised free-space bytes.
    decimal_places = len(match.group(1).replace(',', '.').partition('.')[2])
    tolerance = Decimal(5) * (Decimal(10) ** (-decimal_places - 1))
    free = max(0, int((value - tolerance) * scale))
    reserve = max(MIN_PI_RESERVE, int(free * PI_RESERVE_FRACTION))
    usable = max(0, free - reserve)
    return {'reported': raw.strip(), 'free_bytes': free,
            'reserve_bytes': reserve, 'usable_bytes': usable,
            'usable_gib': f'{usable / GIB:.1f}',
            'reserve_gib': f'{reserve / GIB:.1f}'}


def root_matches_media(url):
    """Operator-attested topology, never inferred from an API response.

    Reconfirm after mount/container changes. Include Django's temporary upload
    filesystem as well as assetdir; both copies must fit the measured root FS.
    """
    verified = os.environ.get('ANTHIAS_VERIFIED_STORAGE_URLS', '').split(',')
    return url.rstrip('/') in {value.strip().rstrip('/') for value in verified if value.strip()}


def upload_capacity(info, url):
    """Expose capacity only for verified topology; retain known zero-space blocks."""
    disk = capacity(info)
    if disk is None:
        return None
    # A single-shot Django upload can coexist with its copy in assetdir.
    disk['usable_bytes'] //= 2
    disk['usable_gib'] = f"{disk['usable_bytes'] / GIB:.1f}"
    if disk['usable_bytes'] == 0 or root_matches_media(url):
        return disk
    return None
