import io
import pytest
from unittest.mock import patch
from app.anthias import Anthias, PlayerError


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.status_code = status_code
        self.content = b'1' if data is not None else b''
        self._data = data

    def json(self):
        return self._data


class RecordingHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == 'POST' and url.endswith('/api/v2/assets'):
            if self.calls[-1][2]['json'].get('is_enabled'):
                return FakeResponse(
                    {
                        'error': (
                            "'<' not supported between instances of 'str' "
                            "and 'datetime.datetime'"
                        )
                    },
                    status_code=500,
                )
            return FakeResponse({'asset_id': 'created-asset'})
        if method == 'POST' and url.endswith('/api/v2/file_asset'):
            return FakeResponse({'uri': '/data/anthias_assets/upload.tmp', 'ext': '.png'})
        return FakeResponse({})


def anthias_with_recording_http():
    client = Anthias({'url': 'http://player.example'})
    recorder = RecordingHttp()
    client.http = recorder
    return client, recorder


def test_create_uses_upstream_asset_contract_and_avoids_legacy_500():
    """Match the upstream UI's safe create-then-enable sequence.

    Anthias commit a7c2d31's React asset form sends ``webpage`` and
    ``is_enabled: 0``.  The v2 server's old create path called
    ``is_active()`` before refreshing the newly-created model, which made an
    enabled POST compare serialized date strings with datetimes (GH #2190).
    """
    client, recorder = anthias_with_recording_http()

    result = client.create('Status board', 'https://example.org/status', 30)

    assert result == {'asset_id': 'created-asset'}
    method, url, kwargs = recorder.calls[0]
    assert (method, url) == ('POST', 'http://player.example/api/v2/assets')
    assert kwargs['json'] == {
        'name': 'Status board',
        'uri': 'https://example.org/status',
        'duration': 30,
        'mimetype': 'webpage',
        'is_enabled': False,
        'is_processing': False,
        'start_date': '2020-01-01T00:00:00Z',
        'end_date': '2099-12-31T23:59:59Z',
    }

    method, url, kwargs = recorder.calls[1]
    assert (method, url) == (
        'PATCH',
        'http://player.example/api/v2/assets/created-asset',
    )
    assert kwargs['json'] == {'is_enabled': True}


def test_create_normalizes_uploaded_media_types_to_upstream_values():
    client, recorder = anthias_with_recording_http()

    client.create(
        'Photo', '/data/anthias_assets/upload.tmp', 15,
        mimetype='image/png', ext='.png',
    )
    client.create(
        'Video', '/data/anthias_assets/movie.tmp', 0,
        mimetype='video/mp4', ext='.mp4',
    )

    asset_posts = [
        call[2]['json'] for call in recorder.calls
        if call[0] == 'POST' and call[1].endswith('/api/v2/assets')
    ]
    assert asset_posts[0]['mimetype'] == 'image'
    assert asset_posts[0]['ext'] == '.png'
    assert asset_posts[1]['mimetype'] == 'video'
    assert asset_posts[1]['ext'] == '.mp4'


def test_upload_uses_the_upstream_multipart_field():
    client, recorder = anthias_with_recording_http()
    storage = io.BytesIO(b'fake-png')

    # Storage must be checked before any upload, then a streaming encoder is
    # sent with the exact upstream field name; no eager requests(files=...)
    with patch.object(client, 'info', return_value={'free_space': '10.0 GB'}):
        result = client.upload(storage, 'photo.png', 'image/png')

    assert result == {'uri': '/data/anthias_assets/upload.tmp', 'ext': '.png'}
    method, url, kwargs = recorder.calls[0]
    assert (method, url) == ('POST', 'http://player.example/api/v2/file_asset')
    assert 'files' not in kwargs
    assert kwargs['data'].content_type.startswith('multipart/form-data')
    assert 'name="file_upload"' in kwargs['data'].to_string().decode('latin1')
    assert kwargs['headers']['Content-Type'] == kwargs['data'].content_type



def test_create_requires_asset_id_before_reporting_success():
    client, recorder = anthias_with_recording_http()
    recorder.request = lambda method, url, **kwargs: FakeResponse({'unexpected': True})
    with pytest.raises(PlayerError, match='Asset-ID'):
        client.create('Site', 'https://example.org', 30)
