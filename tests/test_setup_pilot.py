"""Exercise interrupted setup without a Docker daemon or real credentials."""
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rerun_recovers_missing_account_without_changing_existing_state(tmp_path):
    for name in ("compose.yaml", "compose.cd.yaml", ".env.example"):
        shutil.copy2(ROOT / name, tmp_path / name)
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/setup-pilot.sh", tmp_path / "scripts/setup-pilot.sh")
    (tmp_path / "bin").mkdir()
    docker = tmp_path / "bin/docker"
    docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path.cwd()
args = sys.argv[1:]
with (root / "calls.log").open("a") as f:
    f.write(" ".join(args) + "\\n")
if args[:2] == ["compose", "version"]:
    sys.exit(0)
if args[0] == "compose" and "config" in args:
    print("ghcr.io/ffworker/anthias-hub:sha-test")
    sys.exit(0)
if args[0] == "run":
    role = args[-1]
    if "-c" in args:
        p = root / "config/users.json"
        try:
            users = json.loads(p.read_text())["users"] if p.exists() else []
        except (ValueError, KeyError):
            sys.exit(2)
        sys.exit(0 if any(u["username"] == role for u in users) else 1)
    if role == "marketing" and (root / "fail-once").exists():
        (root / "fail-once").unlink()
        sys.exit(1)
    p = root / "config/users.json"
    users = json.loads(p.read_text())["users"] if p.exists() else []
    users = [u for u in users if u["username"] != role]
    users.append({"username": role, "role": role, "password_hash": "test-hash"})
    p.write_text(json.dumps({"users": users}))
    sys.exit(0)
sys.exit(0)
''')
    docker.chmod(0o755)
    (tmp_path / "bin/ss").write_text('#!/bin/sh\nexit 0\n')
    (tmp_path / "bin/ss").chmod(0o755)
    (tmp_path / "bin/curl").write_text('#!/bin/sh\nprintf ok\n')
    (tmp_path / "bin/curl").chmod(0o755)
    (tmp_path / "fail-once").touch()
    env = dict(os.environ, PATH=str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    cmd = ["bash", str(tmp_path / "scripts/setup-pilot.sh")]
    first = subprocess.run(cmd, cwd=tmp_path, env=env, input="", text=True, capture_output=True)
    assert first.returncode != 0
    users_path = tmp_path / "config/users.json"
    assert [u["username"] for u in json.loads(users_path.read_text())["users"]] == ["it"]
    original_env = (tmp_path / ".env").read_bytes()
    original_user = users_path.read_bytes()

    second = subprocess.run(cmd, cwd=tmp_path, env=env, input="", text=True, capture_output=True)
    assert second.returncode == 0, second.stderr
    assert (tmp_path / ".env").read_bytes() == original_env
    assert [u["username"] for u in json.loads(users_path.read_text())["users"]] == ["it", "marketing"]
    assert b'"username": "it"' in original_user
    calls_before = (tmp_path / "calls.log").read_text()
    users_before = users_path.read_bytes()
    third = subprocess.run(cmd, cwd=tmp_path, env=env, input="", text=True, capture_output=True)
    assert third.returncode == 0, third.stderr
    assert users_path.read_bytes() == users_before
    assert (tmp_path / "calls.log").read_text().count("-m scripts.create_user") == calls_before.count("-m scripts.create_user")

    reset = subprocess.run(cmd + ["--reset-users"], cwd=tmp_path, env=env,
                           input="y\nn\n", text=True, capture_output=True)
    assert reset.returncode == 0, reset.stderr
    reset_calls = (tmp_path / "calls.log").read_text()[len(calls_before):]
    assert reset_calls.count("-m scripts.create_user") == 1
    assert "users.json it it" in reset_calls
    assert (tmp_path / ".env").read_bytes() == original_env

    # A pinned production install must recover users without switching back to pilot.
    with (tmp_path / ".env").open("a") as f:
        f.write("\nANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-test\n")
    users_path.unlink()
    calls_before = (tmp_path / "calls.log").read_text()
    pinned = subprocess.run(cmd, cwd=tmp_path, env=env, input="", text=True, capture_output=True)
    assert pinned.returncode == 0, pinned.stderr
    new_calls = (tmp_path / "calls.log").read_text()[len(calls_before):]
    assert "compose -f compose.cd.yaml -p anthias-hub up -d" in new_calls
    assert "--entrypoint python ghcr.io/ffworker/anthias-hub:sha-test" in new_calls
    assert "compose -p anthias-hub build" not in new_calls
    assert [u["username"] for u in json.loads(users_path.read_text())["users"]] == ["it", "marketing"]

    users_path.write_text("{broken")
    before_bad_run = (tmp_path / "calls.log").read_text()
    bad = subprocess.run(cmd, cwd=tmp_path, env=env, input="", text=True, capture_output=True)
    assert bad.returncode != 0
    assert users_path.read_text() == "{broken"
    assert "-m scripts.create_user" not in (tmp_path / "calls.log").read_text()[len(before_bad_run):]


def test_solo_setup_resumes_as_owner_without_creating_team_accounts(tmp_path):
    for name in ('compose.yaml', 'compose.cd.yaml', '.env.example'):
        shutil.copy2(ROOT / name, tmp_path / name)
    (tmp_path / 'scripts').mkdir()
    shutil.copy2(ROOT / 'scripts/setup-pilot.sh', tmp_path / 'scripts/setup-pilot.sh')
    (tmp_path / 'bin').mkdir()
    docker = tmp_path / 'bin/docker'
    docker.write_text('''#!/usr/bin/env python3
import json, sys
from pathlib import Path
root = Path.cwd()
args = sys.argv[1:]
if args[:2] == ['compose', 'version']: sys.exit(0)
if args[0] == 'compose' and 'config' in args: print('test-image'); sys.exit(0)
if args[0] == 'run':
    role = args[-1]
    p = root / 'config/users.json'
    users = json.loads(p.read_text())['users'] if p.exists() else []
    if '-c' in args: sys.exit(0 if any(u['username'] == role for u in users) else 1)
    users.append({'username': role, 'role': role, 'password_hash': 'test-hash'})
    p.write_text(json.dumps({'users': users})); sys.exit(0)
sys.exit(0)
''')
    docker.chmod(0o755)
    (tmp_path / 'bin/ss').write_text('#!/bin/sh\\nexit 0\\n')
    (tmp_path / 'bin/ss').chmod(0o755)
    (tmp_path / 'bin/curl').write_text('#!/bin/sh\\nprintf ok\\n')
    (tmp_path / 'bin/curl').chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path / 'bin') + os.pathsep + os.environ['PATH'])
    first = subprocess.run(['bash', 'scripts/setup-pilot.sh', '--solo'], cwd=tmp_path, env=env, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    assert [u['role'] for u in json.loads((tmp_path / 'config/users.json').read_text())['users']] == ['owner']
    second = subprocess.run(['bash', 'scripts/setup-pilot.sh'], cwd=tmp_path, env=env, text=True, capture_output=True)
    assert second.returncode == 0, second.stderr
    assert [u['role'] for u in json.loads((tmp_path / 'config/users.json').read_text())['users']] == ['owner']
