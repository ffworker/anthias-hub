"""Privacy guard for the current tracked documentation, not historical Git commits."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_avoid_internal_operational_examples():
    files = [ROOT / "README.md", ROOT / "SECURITY.md"]
    files += list((ROOT / "docs").glob("*.md"))
    files += list((ROOT / "scripts").glob("*.sh"))
    patterns = [
        r"logserv\.local", r"gh-pihub", r"gh-bistro",
        r"github\.com/ffworker/rss2slideshow",
        r"github\.com:ffworker/rss2slideshow",
    ]
    for file in files:
        content = file.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, content, re.IGNORECASE), (file, pattern)


def test_local_markdown_links_resolve():
    files = [ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md"]
    files += list((ROOT / "docs").glob("*.md"))
    for file in files:
        content = file.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            # Only check direct local file links, never external resources.
            if target.startswith("/") or "?" in target:
                continue
            assert (file.parent / target).exists(), (file, target)
