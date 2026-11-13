"""A running build must be identified by image-baked metadata, not .env."""
from app.version import UI_REVISION, read_build_sha


def test_read_build_sha_fails_closed_for_local_or_missing_metadata(tmp_path):
    path = tmp_path / ".build-revision"
    assert read_build_sha(path) is None
    for invalid in ("dev", "sha-", "f00", "latest", "f" * 41,
                    "f" * 39 + "\nmalicious", "🙃"):
        path.write_text(invalid, encoding="utf-8")
        assert read_build_sha(path) is None


def test_read_build_sha_accepts_real_commit_and_normalizes_case(tmp_path):
    path = tmp_path / ".build-revision"
    valid = "aB2C" * 10
    path.write_text(valid + "\n", encoding="utf-8")
    assert read_build_sha(path) == valid.lower()
    assert UI_REVISION == "ui-20261113-08"
