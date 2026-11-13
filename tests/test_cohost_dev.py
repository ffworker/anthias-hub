"""Co-hosted DEV must keep independent ports, Docker project and data."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev-cohost.sh"


def test_cohosted_compose_overrides_do_not_change_pilot_defaults():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    importer = (ROOT / "compose.dev.yaml").read_text(encoding="utf-8")
    helper = SCRIPT.read_text(encoding="utf-8")

    assert "${HUB_BIND_PORT:-8765}" in compose
    assert "${HUB_LOCAL_IMAGE:-anthias-hub:pilot}" in compose
    assert "${HUB_LOCAL_IMAGE:-anthias-hub:pilot}" in importer
    assert "project=anthias-hub-dev" in helper
    assert "image=anthias-hub:dev-cohost" in helper
    assert "port=8766" in helper
    assert "HUB_BIND_PORT=$port" in helper
    assert "HUB_LOCAL_IMAGE=$image" in helper
    assert "ANTHIAS_ALLOWED_CIDRS=127.0.0.0/8" in helper
    assert "DEV_AUTO_PUBLISH=0" in helper
    assert "DEV_PRUNE_MISSING=0" in helper
    assert "FOLDER_SYNC_INTERVAL=60" in helper
    assert 'files=(-f compose.yaml -f compose.dev.yaml)' in helper
    assert 'docker compose -p "$project" "' in helper
    assert 'compose.dev.smb.yaml' in helper
    assert 'dc up -d --no-build --no-deps --force-recreate anthias-hub anthias-folder-import' in helper


def test_dev_cohost_refuses_the_default_checkout_before_docker():
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    # CI repo is not named anthias-hub-dev. Guard returns before Docker access.
    refused = subprocess.run(["bash", str(SCRIPT), "start"],
                             capture_output=True, text=True)
    assert refused.returncode != 0
    assert "separate directory named anthias-hub-dev" in refused.stderr


def test_cohosted_readme_requires_explicit_test_player():
    instructions = (ROOT / "docs" / "cohosted-development.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8766" in instructions
    assert "127.0.0.1:8765" in instructions
    assert "ANTHIAS_ALLOWED_CIDRS=127.0.0.0/8" in instructions
    assert "DEV_AUTO_PUBLISH=1" in instructions
    assert "anthias-hub-dev" in instructions


def test_dev_first_install_does_not_reference_deleted_branch_or_strand_partial_init():
    helper = SCRIPT.read_text(encoding="utf-8")
    cohost = (ROOT / "docs" / "cohosted-development.md").read_text(encoding="utf-8")
    workflow = (ROOT / "docs" / "dev-workflow-v2.md").read_text(encoding="utf-8")
    deleted = "dev/cohosted-staging-isolation-20261113"
    branch = "dev/screen-source-of-truth-v2-20261113"
    assert all(deleted not in text for text in (helper, cohost, workflow))
    assert all(branch in text for text in (helper, cohost, workflow))
    assert "git switch --track origin/" + branch in helper
    assert "DEV setup incomplete" in helper
    assert 'if [[ -f .env && ! -s config/users.json ]]' in helper
    assert "run bash scripts/dev-cohost.sh init" in helper
    assert "Direct editing on managed test screens is allowed." not in cohost
    assert "read-only in DEV v2" in cohost
