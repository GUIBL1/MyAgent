"""MyAgent — 多 agent 协作工具。"""

from pathlib import Path
import sys

# 版本号唯一来源是 pyproject.toml
# 发布后从包元数据读取；PyInstaller 打包后从捆绑的 VERSION 文件读取
try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("myagent")
except Exception:
    _version_file = Path(sys._MEIPASS) / "VERSION" if getattr(sys, "frozen", False) else None
    if _version_file and _version_file.exists():
        __version__ = _version_file.read_text().strip()
    else:
        __version__ = "unknown"
