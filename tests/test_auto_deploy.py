"""Offline tests for the host-side image updater; no Docker daemon needed."""
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import auto_deploy


def setup_checkout(tmp_path):
    for name in ('compose.cd.yaml', '.env', 'config/users.json', 'data/devices.json'):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('fixture')
    return tmp_path


def mock_docker(current_image, new_image):
    calls = []
    state = {'running': current_image, 'tag': new_image}

    def command(args, cwd, *, image=None):
        calls.append((tuple(args), image))
        if args[-3:] == ['ps', '-q', 'anthias-hub']:
            return 'container-id'
        if args[:2] == ['docker', 'inspect']:
            return auto_deploy.MAIN_IMAGE if '.Config.Image' in args[3] else state['running']
        if args[:3] == ['docker', 'image', 'inspect']:
            return state['tag']
        if args[-1] == 'pull':
            return ''
        if args[:3] == ['docker', 'image', 'tag']:
            return ''
        if 'up' in args:
            state['running'] = current_image if image == auto_deploy.ROLLBACK_IMAGE else new_image
            return ''
        raise AssertionError(args)

    return command, calls, state


def test_deploys_new_image_only_after_successful_health_check(tmp_path):
    checkout = setup_checkout(tmp_path)
    cmd, calls, state = mock_docker('sha-old', 'sha-new')
    with patch.object(auto_deploy, 'command', cmd), patch.object(auto_deploy, 'healthy', return_value=True):
        assert auto_deploy.deploy(checkout) == 'updated'
    assert state['running'] == 'sha-new'
    assert any('pull' in args for args, _ in calls)
    assert any('up' in args for args, _ in calls)


def test_failed_health_rolls_back_and_quarantines_image(tmp_path):
    checkout = setup_checkout(tmp_path)
    cmd, calls, state = mock_docker('sha-old', 'sha-bad')
    with patch.object(auto_deploy, 'command', cmd), patch.object(auto_deploy, 'healthy', side_effect=[False, True]):
        with pytest.raises(auto_deploy.DeployError, match='rollback'):
            auto_deploy.deploy(checkout)
    assert state['running'] == 'sha-old'
    assert (checkout / 'data/.cd-rejected').read_text().strip() == 'sha-bad'
    assert any(image == auto_deploy.ROLLBACK_IMAGE for _, image in calls)
    calls.clear()
    with patch.object(auto_deploy, 'command', cmd), patch.object(auto_deploy, 'healthy') as health:
        assert auto_deploy.deploy(checkout) == 'quarantined'
    assert not any('up' in args for args, _ in calls)
    health.assert_not_called()


def test_refuses_cold_start_or_missing_state(tmp_path):
    checkout = setup_checkout(tmp_path)
    (checkout / '.env').unlink()
    with pytest.raises(auto_deploy.DeployError, match='Existing'):
        auto_deploy.deploy(checkout)


def test_no_change_does_not_restart(tmp_path):
    checkout = setup_checkout(tmp_path)
    cmd, calls, _ = mock_docker('sha-same', 'sha-same')
    with patch.object(auto_deploy, 'command', cmd), patch.object(auto_deploy, 'healthy') as health:
        assert auto_deploy.deploy(checkout) == 'unchanged'
    assert not any('up' in args for args, _ in calls)
    health.assert_not_called()


def test_refuses_to_replace_pilot_without_manual_migration(tmp_path):
    checkout = setup_checkout(tmp_path)
    cmd, calls, _ = mock_docker('sha-old', 'sha-new')

    def pilot_command(args, cwd, *, image=None):
        if args[:2] == ['docker', 'inspect'] and '.Config.Image' in args[3]:
            return 'anthias-hub:pilot'
        return cmd(args, cwd, image=image)

    with patch.object(auto_deploy, 'command', pilot_command):
        with pytest.raises(auto_deploy.DeployError, match='migrate'):
            auto_deploy.deploy(checkout)
    assert not any('pull' in args or 'up' in args for args, _ in calls)