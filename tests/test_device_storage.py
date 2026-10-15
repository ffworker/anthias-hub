"""Anthias capacity parsing and upload preflight: offline, no huge allocations."""
import io
from unittest.mock import MagicMock, patch

import pytest
from requests.models import Response
from app.anthias import Anthias, PlayerError
from app.storage import GIB, MAX_MEDIA_BYTES, capacity


@pytest.mark.parametrize(('raw', 'minimum', 'maximum'), [
    ('15.0\u00a0GB', 12 * GIB, 13 * GIB),
    ('3.5 GB', 1 * GIB, 2 * GIB),
    ('600 MB', 0, 0),
    ('12G', 9 * GIB, 10 * GIB),
])
def test_capacity_conservative_headroom(raw, minimum, maximum):
    result = capacity({'free_space': raw})
    assert minimum <= result['usable_bytes'] <= maximum
    assert result['free_bytes'] - result['usable_bytes'] >= 2 * GIB


@pytest.mark.parametrize('value', [None, '', '-2 GB', 'unknown', 'NaN GB', '1e9 GB', 1234, '300%'])
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
        with pytest.raises(PlayerError, match='nicht zuverlässig'):
            api.upload(io.BytesIO(b'1234'), 'x.mp4', 'video/mp4')
    api.http.request.assert_not_called()
