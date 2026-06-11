#!/usr/bin/env bash
set -euo pipefail

source ~/.zshrc

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

current_date=$(date +%Y-%m-%d)

python3 LPL_T.py
python3 convert_to_ics.py

# if git diff --cached --quiet; then
#   echo "没有检测到变更，跳过提交和推送。"
#   exit 0
# fi

git add .

git commit -m "LPL $current_date"
git push
