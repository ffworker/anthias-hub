"""Anthias capacity parsing and upload preflight: offline, no huge allocations."""
import io
from unittest.mock import MagicMock, patch

import pytest
from app.anthias import Anthias, PlayerError
from app.storage import GIB, MAX_MEDIA_BYTES, capacity


@pytest.mark.parametrize(('raw', 'minimum', 'maximum'), [
    ('15.0\u00a0GB', 11 * GIB, 12 * GIB),
    ('3.5 GB', 1 * GIB, 2 * GIB),
    ('600 MB', 0, 0),
    ('12G', 9 * GIB, 10 * GIB),
])
def test_capacity_conservative_headroom(raw, minimum, maximum):
    result = capacity({'free_space': raw})
    assert minimum <= result['usable_bytes'] <= maximum
    assert result['reserve_bytes'] >= 2 * GIB
    assert result['usable_bytes'] <= max(0, result['free_bytes'] - result['reserve_bytes'])


@pytest.mark.parametrize('value', [None, '', '-2 GB', 'unknown', 'NaN GB', '1e9 GB', '300%'])
def test_capacity_unknown_fails_closed(value):
    assert capacity({'free_space': value}) is None


def test_streaming_upload_preflights_and_uses_toolbelt():
    api = Anthias({'url': 'http://127.0.0.1'})
    response = MagicMock(status_code=200, content=b'{"uri": "file:///test.mp4"}')
    response.json.return_value = {'uri': 'file:///test.mp4'}
    api.http.request = MagicMock(return_value=response)
    with patch.object(api, 'info', return_value={'free_space': '10.0 GB'}):
        result = api.upload(io.BytesIO(b'\x00\x00\x00\x18ftyp' + b'x' * 1024),
                            'sample.mp4', 'video/mp4')
    assert result['uri'] == 'file:///test.mp4'
    kwargs = api.http.request.call_args.kwargs
    assert kwargs['data'].content_type.startswith('multipart/form-data')
    assert kwargs['timeout'][1] >= 900
    assert 'files' not in kwargs


def test_insufficient_space_blocks_before_transfer():
    api = Anthias({'url': 'http://127.0.0.1'})
    api.http.request = MagicMock()
    with patch.object(api, 'info', return_value={'free_space': '2.0 GB'}):
        with pytest.raises(PlayerError, match='Zu wenig'):
            api.upload(io.BytesIO(b'1234'), 'x.mp4', 'video/mp4')
    api.http.request.assert_not_called()


def test_unknown_space_blocks_before_transfer():
    api = Anthias({'url': 'http://127.0.0.1'})
    api.http.request = MagicMock()
    with patch.object(api, 'info', return_value={}):
        with pytest.raises(PlayerError, match='Speicherprüfung fehlgeschlagen'):
            api.upload(io.BytesIO(b'1234'), 'x.mp4', 'video/mp4')
    api.http.request.assert_not_called()


def test_storage_report_has_zero_usable_below_reserve():
    cap = capacity({'free_space': '1.9 GB'})
    assert cap['usable_bytes'] == 0
    assert cap['reserve_bytes'] >= 2 * GIB


def test_upload_rejects_more_than_4_gib_before_contacting_player():
    class VirtualFile:
        def __init__(self):
            self.position = 0
        def tell(self):
            return self.position
        def seek(self, position, mode=0):
            self.position = MAX_MEDIA_BYTES + 1 if mode == 2 else position
    api = Anthias({'url': 'http://127.0.0.1'})
    api.http.request = MagicMock()
    with pytest.raises(PlayerError, match='größer als 4 GiB'):
        api.upload(VirtualFile(), 'oversized.mp4', 'video/mp4')
    api.http.request.assert_not_called()


def test_legacy_locale_and_integer_bytes_capacity():
    comma = capacity({'free_space': '15,0\u00a0GB'})
    assert 11 * GIB < comma['usable_bytes'] < 12 * GIB
    numeric = capacity({'free_space': 8 * GIB})
    assert numeric['free_bytes'] == 8 * GIB
    assert numeric['usable_bytes'] < numeric['free_bytes']
    assert capacity({'free_space': True}) is None


def test_unknown_storage_requires_explicit_override():
    api = Anthias({'url': 'http://127.0.0.1'})
    response = MagicMock(status_code=200, content=b'{"uri": "file:///test.mp4"}')
    response.json.return_value = {'uri': 'file:///test.mp4'}
    api.http.request = MagicMock(return_value=response)
    with patch.object(api, 'info', side_effect=PlayerError('Anthias antwortete mit HTTP 404')):
        with pytest.raises(PlayerError, match='Speicherprüfung fehlgeschlagen'):
            api.upload(io.BytesIO(b'test'), 'small.mp4', 'video/mp4')
        result = api.upload(io.BytesIO(b'test'), 'small.mp4', 'video/mp4',
                            allow_unknown_space=True)
    assert result['uri'] == 'file:///test.mp4'
    assert api.http.request.call_count == 1


def test_known_insufficient_space_still_blocks_with_override():
    api = Anthias({'url': 'http://127.0.0.1'})
    api.http.request = MagicMock()
    with patch.object(api, 'info', return_value={'free_space': '2.0 GB'}):
        with pytest.raises(PlayerError, match='Zu wenig'):
            api.upload(io.BytesIO(b'test'), 'small.mp4', 'video/mp4',
                       allow_unknown_space=True)
    api.http.request.assert_not_called()


@pytest.fixture(autouse=True)
def verified_test_topology(monkeypatch):
    monkeypatch.setenv('ANTHIAS_VERIFIED_STORAGE_URLS', 'http://127.0.0.1,http://10.0.0.42')


def test_unverified_root_requires_override_even_with_plenty_of_space(monkeypatch):
    monkeypatch.delenv('ANTHIAS_VERIFIED_STORAGE_URLS')
    api = Anthias({'url': 'http://127.0.0.1'})
    response = MagicMock(status_code=200, content=b'{}')
    response.json.return_value = {'uri': '/media/test.tmp'}
    api.http.request = MagicMock(return_value=response)
    with patch.object(api, 'info', return_value={'free_space': '10.0 GB'}):
        with pytest.raises(PlayerError, match='Zuordnung'):
            api.upload(io.BytesIO(b'test'), 'x.mp4', 'video/mp4')
        api.http.request.assert_not_called()
        api.upload(io.BytesIO(b'test'), 'x.mp4', 'video/mp4', allow_unknown_space=True)
    assert api.http.request.call_count == 1


def test_double_copy_preflight_blocks_before_transfer_even_with_override(monkeypatch):
    # Exactly one file fits above the reserve, but Django needs two copies.
    class SizedStream(io.BytesIO):
        def seek(self, offset, whence=0):
            if whence == 2:
                return super().seek(GIB)
            return super().seek(offset, whence)
    api = Anthias({'url': 'http://127.0.0.1'})
    api.http.request = MagicMock()
    for configured in ('http://127.0.0.1', ''):
        monkeypatch.setenv('ANTHIAS_VERIFIED_STORAGE_URLS', configured)
        with patch.object(api, 'info', return_value={'free_space': 3 * GIB}):
            with pytest.raises(PlayerError, match='zwei Dateikopien'):
                api.upload(SizedStream(b'test'), 'x.mp4', 'video/mp4', allow_unknown_space=True)
    api.http.request.assert_not_called()


def test_capacity_locale_rounding_is_identical():
    assert capacity({'free_space': '15,0 GB'})['free_bytes'] == capacity({'free_space': '15.0 GB'})['free_bytes']


def test_upload_capacity_requires_exact_verified_url(monkeypatch):
    from app.storage import upload_capacity
    monkeypatch.setenv('ANTHIAS_VERIFIED_STORAGE_URLS', 'http://192.168.1.10/')
    assert upload_capacity({'free_space': 8 * GIB}, 'http://192.168.1.10')['usable_bytes'] == 3 * GIB
    assert upload_capacity({'free_space': 8 * GIB}, 'http://192.168.1.100') is None
    assert upload_capacity({'free_space': GIB}, 'http://192.168.1.100')['usable_bytes'] == 0



def test_4_gib_policy_agrees_for_player_library_batch_and_backup():
    from app.storage import MAX_REQUEST_BYTES, MIB
    from app.library import MAX_MEDIA, MAX_ARCHIVE
    from app.bulk_media import MAX_BATCH_BYTES
    assert MAX_MEDIA_BYTES == 4 * GIB
    assert MAX_MEDIA == MAX_BATCH_BYTES == MAX_MEDIA_BYTES
    assert MAX_REQUEST_BYTES == MAX_MEDIA_BYTES + 16 * MIB
    assert MAX_MEDIA_BYTES < MAX_ARCHIVE < MAX_REQUEST_BYTES


def test_exact_4_gib_synthetic_stream_stays_streaming_and_can_be_accepted():
    """No huge allocation: metadata-only virtual stream and mocked HTTP transport."""
    class VirtualFourGiB:
        def __init__(self):
            self.position = 0
            # requests-toolbelt needs a known content length to stream a file.
            self.len = 4 * GIB
        def tell(self):
            return self.position
        def seek(self, offset, whence=0):
            self.position = 4 * GIB + offset if whence == 2 else offset
            return self.position
        def read(self, n=-1):
            raise AssertionError('4 GiB payload must not be read during setup')
    api = Anthias({'url': 'http://127.0.0.1'})
    response = MagicMock(status_code=200, content=b'{"uri": "/media/test.mp4"}')
    response.json.return_value = {'uri': '/media/test.mp4'}
    api.http.request = MagicMock(return_value=response)
    with patch.object(api, 'info', return_value={'free_space': 20 * GIB}):
        result = api.upload(VirtualFourGiB(), 'test.mp4', 'video/mp4')
    assert result['uri'] == '/media/test.mp4'
    encoder = api.http.request.call_args.kwargs['data']
    # requests-toolbelt exposes .len; it is not a Python sized collection.
    assert encoder.len > 4 * GIB
