"""Release metadata baked into each published Docker image.

Never infer the running version from a checkout, the Compose .env image tag,
or a moving registry tag: those can differ from the running container.
"""
import re
from pathlib import Path

UI_REVISION = "ui-20261113-05"
BUILD_SHA_FILE = Path(__file__).resolve().parent.parent / ".build-revision"


def read_build_sha(path=BUILD_SHA_FILE):
    """Return the exact published Git commit, or None for a local/unmarked build."""
    try:
        value = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    if not re.fullmatch(r"[a-fA-F0-9]{40}", value):
        return None
    return value.lower()
