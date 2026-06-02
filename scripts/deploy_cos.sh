#!/bin/bash
# 部署到腾讯云 COS
# 用法: bash scripts/deploy_cos.sh
set -e
cd "$(dirname "$0")/.."

echo "=== 构建数据 ==="
python -m src.guoan_builder

echo "=== 上传到 COS ==="
# 同步 web/ 目录到 COS bucket
# 配置方式: coscmd config -a <SecretId> -s <SecretKey> -b <BucketName> -r <Region>
coscmd upload -r web/ / --delete

echo "=== 部署完成 ==="
echo "访问地址: https://<你的域名>/index.html"
echo "或 COS 静态网站地址"
