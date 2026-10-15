"""The single rolling GHCR tag is latest; SHA snapshots remain available."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_latest_is_only_rolling_channel():
    workflow = (ROOT / '.github/workflows/tests.yml').read_text()
    assert 'ghcr.io/ffworker/anthias-hub:latest' in workflow
    assert 'ghcr.io/ffworker/anthias-hub:sha-' in workflow
    assert 'ghcr.io/ffworker/anthias-hub:main' not in workflow
    assert 'ghcr.io/ffworker/anthias-hub:stable' not in workflow
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert 'ghcr.io/ffworker/anthias-hub:latest' in (ROOT / 'compose.cd.yaml').read_text()
