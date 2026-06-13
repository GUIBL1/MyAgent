#!/bin/bash
# PyInstaller 一键构建脚本
# 从 pyproject.toml 提取版本号注入 VERSION 文件，构建完成后清理
set -e

echo "=== 提取版本号 ==="
python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" > VERSION
echo "版本: $(cat VERSION)"

if [ ! -d frontend/dist ]; then
    echo "=== 构建前端 ==="
    cd frontend
    npm ci
    npm run build
    cd ..
else
    echo "=== 前端已有 dist/，跳过构建 ==="
fi

echo "=== PyInstaller 打包 ==="
pyinstaller myagent.spec --clean

rm VERSION
echo "=== 完成 ==="
echo "二进制文件: dist/myagent"
echo "验证: dist/myagent --version"
dist/myagent --version
