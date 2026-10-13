"""Restricted integration: only asset endpoints; never proxy arbitrary device paths."""
import re
from urllib.parse import urlsplit
import requests

ASSET_ID = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')
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
        return self.call('GET', '/api/v2/info', timeout=3)

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

    def upload(self, storage, filename, mimetype):
        result = self.call('POST', '/api/v2/file_asset', files={'file_upload': (filename, storage, mimetype)}, timeout=120)
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
