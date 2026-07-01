#!/usr/bin/env bash
set -euo pipefail

source ~/.zshrc

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

current_date=$(date +%Y-%m-%d)

/opt/homebrew/bin/python3 LPL_T.py
/opt/homebrew/bin/python3 convert_to_ics.py

# git add LPL_T.py convert_to_ics.py auto_lpl.sh README.md .gitignore LPL赛程.ics BLG赛程.ics json.json

git add .

if git diff --cached --quiet; then
  echo "没有检测到变更，跳过提交和推送。"
  exit 0
fi

git commit -m "LPL $current_date"
git push origin main

exit 0