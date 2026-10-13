#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
name="${1:-anthias-hub}"
if ! command -v gh >/dev/null; then
  echo 'GitHub CLI (gh) is required: https://cli.github.com/' >&2
  exit 1
fi
gh auth status >/dev/null || { echo 'Please run: gh auth login' >&2; exit 1; }
if [[ ! -d .git ]]; then
  git init -b main
  git add .
  git commit -m 'feat: initial Anthias Hub with static IT and Marketing roles'
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Working tree not clean: review and commit changes before publication.' >&2
  exit 1
fi
if git remote get-url origin >/dev/null 2>&1; then
  echo 'Origin already configured; refusing to create a different repository.' >&2
  exit 1
fi
if git ls-files | grep -E '(^|/)(\.env$|users\.json$|devices\.json$|audit\.jsonl$)' ; then
  echo 'Sensitive runtime files are tracked. Refusing public push.' >&2
  exit 1
fi
printf 'This will CREATE a PUBLIC GitHub repository: %s\n' "$name"
printf 'The linked RSS2Slideshow repository may still be private.\n'
read -r -p 'Type PUBLISH to continue: ' reply
[[ "$reply" == PUBLISH ]] || { echo 'Canceled'; exit 1; }
gh repo create "$name" --public --source=. --remote=origin --push
printf 'Created public repository. Remember to link its actual URL from RSS2Slideshow README.\n'
