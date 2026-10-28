#!/usr/bin/env bash
# 本地入口：优先用 vault 外的 venv，避免把几百 MB 依赖塞进 iCloud 同步目录。
#
#   bash run.sh --doctor
#   bash run.sh --input "<链接或标题>" --out-dir "<输出目录>"
#
# 依赖装在 ~/.local/share/podcast-transcript-txt/venv（见 SKILL.md 末尾的 Local install notes）。
# 若该 venv 不存在，则回退到系统 python3，并在缺少依赖时由 --doctor 明确报 FAIL。

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${PODCAST_SKILL_HOME:-$HOME/.local/share/podcast-transcript-txt}"
VENV="${PODCAST_SKILL_VENV:-$BASE/venv}"

if [ -x "$VENV/bin/python" ]; then
  PY="$VENV/bin/python"
  # doctor 用 shutil.which("yt-dlp") 找可执行文件，所以 venv/bin 必须进 PATH，
  # 否则依赖装好了仍会被判 FAIL。
  export PATH="$VENV/bin:$PATH"
else
  PY="${PYTHON:-python3}"
  echo "WARN: 未找到 ${VENV}/bin/python，回退到 ${PY}；ASR/yt-dlp 依赖可能缺失。" >&2
fi

: "${PODCAST_ASR_MODEL_ROOT:=$BASE/models}"
export PODCAST_ASR_MODEL_ROOT
export PYTHONDONTWRITEBYTECODE=1

exec "$PY" "$HERE/scripts/podcast_transcript_txt.py" "$@"
