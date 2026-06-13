# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — 将前后端打包为单个可执行文件。

使用 scripts/build.sh 一键构建，或手动：
  1. python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" > VERSION
  2. cd frontend && npm run build && cd ..
  3. pyinstaller myagent.spec --clean
  4. rm VERSION
  5. ./dist/myagent
"""

a = Analysis(
    ['agents/core/web_server.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('VERSION', '.'),
        ('frontend/dist', 'frontend/dist'),
    ],
    hiddenimports=[
        # uvicorn 动态加载的 loop / protocol / lifespan 实现
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.auto',
        # chromadb 及其子模块
        'chromadb',
        'chromadb.db',
        'chromadb.api',
        'chromadb.utils.embedding_functions',
        # MCP 协议库
        'mcp',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='myagent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
