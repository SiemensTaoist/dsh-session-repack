#!/usr/bin/env bash
# DSH 会话重压 —— 安装 cron 任务（Linux / macOS）
# 用法：bash install-unix.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python)"
THRESHOLD="${THRESHOLD:-20}"

if [ -z "${PY:-}" ]; then
  echo "找不到 python3，请先安装 Python 3.9+"
  exit 1
fi

if ! "$PY" -c "import zstandard" 2>/dev/null; then
  echo "[*] 安装依赖 zstandard ..."
  "$PY" -m pip install --user zstandard || {
    echo "[!] 装不上，试试：$PY -m pip install --break-system-packages zstandard"
    exit 1
  }
fi

LINE="0 4 * * * $PY $DIR/repack.py --restart --threshold-mb $THRESHOLD >> \$HOME/.dsh/repack-cron.log 2>&1"

echo "[*] 将要加入 crontab："
echo "    $LINE"

( crontab -l 2>/dev/null | grep -v "repack.py" ; echo "$LINE" ) | crontab -

echo
echo "完成。现在可以试跑："
echo "  $PY $DIR/repack.py --dry"
echo "卸载：crontab -e 删掉那一行，或 crontab -l | grep -v repack.py | crontab -"
