#!/usr/bin/env bash
# 장비별 config.yaml을 기본 설정에서 최초 한 번만 생성합니다.
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$PROJECT_ROOT/config.example.yaml"
CONFIG="$PROJECT_ROOT/config.yaml"

if [ -e "$CONFIG" ]; then
  echo "== Keeping existing config.yaml =="
else
  cp "$TEMPLATE" "$CONFIG"
  echo "== Created config.yaml =="
fi
