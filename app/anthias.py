"""Restricted integration: only asset endpoints; never proxy arbitrary device paths."""
import re
import threading
from urllib.parse import urlsplit
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from .storage import MAX_MEDIA_BYTES, capacity, root_matches_media

ASSET_ID = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')
_upload_lock = threading.Lock()  # one upload at a time in the single-worker Hub
DEFAULT_FROM = '2020-01-01T00:00:00Z'
DEFAULT_TO = '2099-12-31T23:59:59Z'

class PlayerError(RuntimeError):
    pass

class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)

class Anthias:
    def __init__(self, device):
        self.url = device['url'].rstrip('/')
        self.http = NoRedirectSession()
        self.http.trust_env = False  # do not route internal management through inherited proxies

    def call(self, method, path, *, payload=None, files=None, timeout=6):
        if not path.startswith('/api/v2/'):
            raise PlayerError('Nur die Anthias-API v2 ist erlaubt')
        try:
            response = self.http.request(method, self.url + path, json=payload, files=files, timeout=timeout)
            if not 200 <= response.status_code < 300:
                raise PlayerError('Anthias antwortete mit HTTP ' + str(response.status_code))
            if len(response.content) > 2_000_000:
                raise PlayerError('Anthias-Antwort zu groß')
            return response.json() if response.content else None
        except (requests.RequestException, ValueError) as exc:
            raise PlayerError('Anthias nicht erreichbar oder ungültige Antwort') from exc

    def assets(self):
        data = self.call('GET', '/api/v2/assets')
        if not isinstance(data, list):
            raise PlayerError('Unerwartetes Assetformat; API-Version prüfen')
        return sorted(data, key=lambda a: (a.get('play_order') or 0, a.get('name') or ''))

    def info(self):
        # The upstream info view may wait for Pi network/host diagnostics.
        # The former 3s limit caused false 'storage unavailable' reports.
        return self.call('GET', '/api/v2/info', timeout=(5, 25))

    def display_power(self, state):
        """Experimental HDMI-CEC control on newer Anthias versions only."""
        if state not in ('on', 'off'):
            raise PlayerError('Ungültiger HDMI-Befehl')
        return self.call('POST', '/api/v2/display/' + state, timeout=8)

    def system_power(self, action):
        """Trigger system action on a registered Pi; never use arbitrary paths."""
        if action not in ('reboot', 'shutdown'):
            raise PlayerError('Ungültiger Gerätebefehl')
        return self.call('POST', '/api/v2/' + action, timeout=8)

    def create(self, name, uri, duration, mimetype='webpage', ext=None):
        body = {
            'name': name, 'uri': uri, 'duration': duration,
            'mimetype': self._asset_mimetype(mimetype),
            # Anthias' pre-refresh v2 create path can compare the serialized
            # date strings in its newly-created instance with datetimes when
            # is_enabled is true (upstream GH #2190).  The native UI also
            # creates disabled; enabling only after persistence keeps this
            # compatible with both the fixed and older API implementations.
            'is_enabled': False, 'is_processing': False,
            'start_date': DEFAULT_FROM, 'end_date': DEFAULT_TO,
        }
        if ext:
            body['ext'] = ext
        result = self.call('POST', '/api/v2/assets', payload=body, timeout=15)
        if not isinstance(result, dict) or not result.get('asset_id'):
            raise PlayerError('Anthias-Antwort enthält keine Asset-ID; Playlist prüfen, bevor du erneut speicherst')
        self.patch(result['asset_id'], {'is_enabled': True})
        return result

    @staticmethod
    def _asset_mimetype(mimetype):
        if mimetype == 'text/html':
            return 'webpage'
        if mimetype.startswith('image/'):
            return 'image'
        if mimetype.startswith('video/'):
            return 'video'
        return mimetype

    def upload(self, storage, filename, mimetype, *, allow_unknown_space=False):
        """Preflight actual Pi capacity and stream multipart without copying into RAM.

        The storage estimate is refreshed for EACH upload under a lock to prevent
        races between Hub uploads in the default single-worker deployment.
        Other external uploaders on the Pi remain outside our control.
        """
        try:
            initial = storage.tell()
            storage.seek(0, 2)
            length = storage.tell() - initial
            storage.seek(initial)
        except (OSError, ValueError, AttributeError) as exc:
            raise PlayerError('Upload-Datei ist nicht lesbar') from exc
        if not 0 < length <= MAX_MEDIA_BYTES:
            raise PlayerError('Medium ist leer oder größer als 1 GiB')
        with _upload_lock:
            try:
                status = capacity(self.info())
            except PlayerError:
                status = None
            # Known shortage is never overridden, even with unverified mounts.
            if status is not None and 2 * length > status['usable_bytes']:
                raise PlayerError(
                    f'Zu wenig freier Speicher auf Anthias ({status["reported"]} gemeldet, '
                    f'{status["reserve_gib"]} GiB Sicherheitsreserve). '
                    'Upload benötigt vorübergehend zwei Dateikopien. '
                    'Vor einem erneuten Upload Playlist und Pi-Speicher prüfen.')
            if (status is None or not root_matches_media(self.url)) and not allow_unknown_space:
                raise PlayerError(
                    'Speicherprüfung fehlgeschlagen: Messung oder Zuordnung von Root-, '
                    'Medien- und Upload-Dateisystem nicht bestätigt. Erneut prüfen oder '
                    'nach manueller Kontrolle des Pi-Speichers „Prüfung ignorieren“ bestätigen.')
            encoder = MultipartEncoder(
                fields={'file_upload': (filename, storage, mimetype)})
            try:
                response = self.http.request(
                    'POST', self.url + '/api/v2/file_asset',
                    data=encoder, headers={'Content-Type': encoder.content_type},
                    timeout=(8, 900))
                if not 200 <= response.status_code < 300:
                    raise PlayerError('Anthias antwortete mit HTTP ' + str(response.status_code))
                if len(response.content) > 2_000_000:
                    raise PlayerError('Anthias-Antwort zu groß')
                result = response.json() if response.content else None
            except (requests.RequestException, ValueError) as exc:
                raise PlayerError('Anthias-Upload unterbrochen oder ungültige Antwort; Playlist vor erneutem Versuch prüfen') from exc
            if not isinstance(result, dict) or not result.get('uri'):
                raise PlayerError('Upload-Antwort enthält keine Medienadresse')
            return result

    def patch(self, asset_id, changes):
        self.valid_id(asset_id)
        return self.call('PATCH', '/api/v2/assets/' + asset_id, payload=changes)

    def remove(self, asset_id):
        self.valid_id(asset_id)
        return self.call('DELETE', '/api/v2/assets/' + asset_id)

    def order(self, ids):
        if not ids or any(not ASSET_ID.fullmatch(i) for i in ids):
            raise PlayerError('Ungültige Playlist-Elemente')
        return self.call('POST', '/api/v2/assets/order', payload={'ids': ','.join(ids)})

    @staticmethod
    def valid_id(asset_id):
        if not ASSET_ID.fullmatch(asset_id):
            raise PlayerError('Ungültige Asset-ID')


def validate_website_url(url):
    url = str(url).strip()
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password or len(url) > 2048:
        raise ValueError('Bitte eine gültige http(s)-Webadresse ohne Zugangsdaten angeben')
    return url


def validate_duration(value):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError('Dauer muss eine Zahl sein') from None
    if n < 5 or n > 3600:
        raise ValueError('Dauer muss zwischen 5 und 3600 Sekunden liegen')
    return n
