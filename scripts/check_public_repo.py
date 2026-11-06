#!/usr/bin/env python3
"""Fail closed on obvious confidential artifacts in *tracked* public files.

This is a CI tripwire, not a substitute for a full Git history scan,
a review of PDFs/images, or secret rotation after accidental disclosure.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DANGEROUS_NAMES = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\..*)?|users\.json|devices\.json|"
    r"media-sources\.json|mount-status\.json|id_rsa|id_ed25519|"
    r"credentials(?:\..*)?|.*\.(?:p12|pfx|pem|key))$"
)
ALLOW_FILENAMES = {".env.example"}
PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|github_pat_)[A-Za-z0-9_]{24,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{24,}")),
    ("payment secret", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}")),
    ("company-style host alias", re.compile(r"\bGH-[A-Za-z][A-Za-z0-9_-]{2,}\b")),
    ("internal employer DNS", re.compile(r"\blog" + r"serv\.(?:local|biz|internal)\b", re.I)),
    ("specific internal subnet", re.compile(r"\b172\.17\.(?:0|1)\.[0-9]{1,3}\b")),
]
TEXT_SUFFIXES = {
    ".md", ".py", ".html", ".css", ".js", ".cjs", ".sh", ".json",
    ".toml", ".yaml", ".yml", ".txt", ".env", ".ini", ".cfg", ".xml", ".svg",
}
TEXT_NAMES = {".env.example", ".dockerignore", ".gitignore", ".gitkeep", "Dockerfile", "LICENSE"}
MAX_BYTES = 5 * 1024 * 1024


def main() -> int:
    try:
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Unable to inspect tracked files: {exc}", file=sys.stderr)
        return 2
    findings = []
    uninspected = []
    for raw in output.split(b"\x00"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="replace")
        path = ROOT / relative
        if path.name not in ALLOW_FILENAMES and DANGEROUS_NAMES.search(relative):
            findings.append((relative, "private runtime/credential filename"))
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES or (path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES):
            uninspected.append(relative)
            continue
        blob = path.read_bytes()
        if b"\x00" in blob:
            uninspected.append(relative)
            continue
        text = blob.decode("utf-8", errors="replace")
        # Every match is shown only by file:line and a category, not by value.
        for category, expression in PATTERNS:
            for match in expression.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append((f"{relative}:{line}", category))
    for where, category in findings:
        print(f"BLOCK: {where}: {category}")
    if uninspected:
        print(f"Manual review still needed for {len(uninspected)} non-text/large tracked file(s).")
        for name in uninspected[:30]:
            print(f"  REVIEW: {name}")
    if findings:
        print("Public tree audit failed. Rotate actual leaked secrets; cleaning HEAD does not clean Git history.")
        return 1
    print("Public tracked text: no configured red flags found. This is NOT a complete secret/history audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
