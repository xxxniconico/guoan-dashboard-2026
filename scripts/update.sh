#!/bin/bash
# 国安仪表盘本地构建脚本
# 用法: bash scripts/update.sh
set -e
cd "$(dirname "$0")/.."
echo "=== 国安仪表盘数据更新 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
python -m src.guoan_builder
echo "=== 完成 ==="
echo "本地预览: cd web && python -m http.server 8080"
