#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python3가 필요합니다. 설치 후 다시 실행해주세요." >&2
  exit 1
fi

if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
  echo "Tkinter를 찾을 수 없습니다. 다음 중 하나로 설치하세요:" >&2
  echo "  - Homebrew: brew install python-tk" >&2
  echo "  - 또는 python.org 공식 인스톨러 사용" >&2
  exit 1
fi

exec "$PYTHON" app.py "$@"
