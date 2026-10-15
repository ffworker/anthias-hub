"""Pull-only Anthias Hub deployment with local health verification and rollback.

Run as the account which owns the checkout and can access the Docker socket.
No SSH from GitHub into the server is required.
"""
import fcntl
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LATEST_IMAGE = 'ghcr.io/ffworker/anthias-hub:latest'
LEGACY_MAIN_IMAGE = 'ghcr.io/ffworker/anthias-hub:main'
GHCR_SHA_PREFIX = 'ghcr.io/ffworker/anthias-hub:sha-'
ROLLBACK_IMAGE = 'anthias-hub:rollback'
PROJECT = 'anthias-hub'
HEALTH = 'http://127.0.0.1:8765/healthz'


class DeployError(RuntimeError):
    pass


def command(args, cwd, *, image=None):
    env = os.environ.copy()
    env['ANTHIAS_HUB_IMAGE'] = image or LATEST_IMAGE
    try:
        return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=180).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Docker diagnostics are local only; do not print the environment or .env.
        raise DeployError('Command failed: ' + ' '.join(args)) from exc


def healthy():
    for attempt in range(12):
        try:
            with urllib.request.urlopen(HEALTH, timeout=3) as response:
                if response.status == 200 and response.read(16) == b'ok\n':
                    return True
        except (OSError, urllib.error.URLError):
            pass
        if attempt < 11:
            time.sleep(5)
    return False


def compose_override(checkout):
    """Read one explicit host-local Compose file without evaluating .env as shell."""
    values = [line.partition('=')[2].strip() for line in (checkout / '.env').read_text().splitlines()
              if line.startswith('HUB_COMPOSE_OVERRIDE=')]
    if not values or not values[-1]:
        return []
    target = Path(values[-1])
    if not target.is_absolute() or not target.is_file():
        raise DeployError('HUB_COMPOSE_OVERRIDE must point to an existing absolute file')
    return ['-f', str(target)]


def managed_image(image):
    """Accept existing Hub GHCR images, including pinned SHA installs, for migration.

    Never auto-adopt a local :pilot or another application's container.
    """
    return (image in (LATEST_IMAGE, LEGACY_MAIN_IMAGE, ROLLBACK_IMAGE)
            or bool(re.fullmatch(re.escape(GHCR_SHA_PREFIX) + r'[0-9a-f]{40}', image)))


def deploy(checkout):
    checkout = Path(checkout).resolve()
    required = ('compose.cd.yaml', '.env', 'config/users.json', 'data/devices.json')
    if any(not (checkout / name).is_file() for name in required):
        raise DeployError('Existing Hub configuration and data are required; never use CD for initial setup')

    compose = ['docker', 'compose', '-f', 'compose.cd.yaml'] + compose_override(checkout) + ['-p', PROJECT]
    container = command(compose + ['ps', '-q', PROJECT], checkout)
    if not container:
        raise DeployError('No running Hub service; migrate and verify it manually first')
    configured = command(['docker', 'inspect', '--format', '{{.Config.Image}}', container], checkout)
    if not managed_image(configured):
        raise DeployError('Hub is not running a known GHCR Hub image; migrate from :pilot manually first')
    previous = command(['docker', 'inspect', '--format', '{{.Image}}', container], checkout)
    command(compose + ['pull'], checkout)
    candidate = command(['docker', 'image', 'inspect', '--format', '{{.Id}}', LATEST_IMAGE], checkout)
    if not candidate or not previous:
        raise DeployError('Could not inspect the deployed or downloaded image')
    if candidate == previous:
        return 'unchanged'
    rejected = checkout / 'data/.cd-rejected'
    if rejected.exists() and rejected.read_text().strip() == candidate:
        return 'quarantined'

    try:
        command(compose + ['up', '-d', '--no-deps', '--force-recreate', PROJECT], checkout)
        running = command(compose + ['ps', '-q', PROJECT], checkout)
        if (not running or
                command(['docker', 'inspect', '--format', '{{.Image}}', running], checkout) != candidate or
                not healthy()):
            raise DeployError('New image did not pass the local health check')
    except DeployError as cause:
        try:
            command(['docker', 'image', 'tag', previous, ROLLBACK_IMAGE], checkout)
            command(compose + ['up', '-d', '--no-deps', '--force-recreate', PROJECT],
                    checkout, image=ROLLBACK_IMAGE)
            running = command(compose + ['ps', '-q', PROJECT], checkout)
            if (not running or
                    command(['docker', 'inspect', '--format', '{{.Image}}', running], checkout) != previous or
                    not healthy()):
                raise DeployError('Rollback image did not pass the local health check')
            rejected.write_text(candidate + '\n')
        except (DeployError, OSError) as rollback_error:
            raise DeployError('Deploy failed; rollback failed. Inspect the Hub immediately') from rollback_error
        raise DeployError('Deploy failed; rollback succeeded. Image quarantined: ' + candidate) from cause

    if rejected.exists():
        rejected.unlink()
    return 'updated'


def main():
    checkout = Path(__file__).resolve().parent.parent
    try:
        with (checkout / '.cd.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            outcome = deploy(checkout)
        print('Anthias Hub deployment:', outcome)
        return 0
    except (OSError, DeployError) as exc:
        print('Anthias Hub deployment ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
