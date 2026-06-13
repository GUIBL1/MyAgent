#!/usr/bin/env python3
"""根据已构建的二进制文件计算 SHA256，生成 Homebrew formula.rb。

用法：python scripts/generate-formula.py 0.1.0 > formula.rb
"""

import hashlib
import sys
from pathlib import Path


DIST_DIR = Path("dist")

# 平台 → 二进制文件名映射
PLATFORMS = {
    "darwin-x86_64": "myagent-darwin-x86_64",
    "linux-x86_64": "myagent-linux-x86_64",
}

REPO = "GUIBL1/MyAgent"


def sha256(path: Path) -> str:
    """计算文件 SHA256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(version: str) -> str:
    """生成 Homebrew formula Ruby 脚本内容。"""
    lines = [
        'class Myagent < Formula',
        f'  desc "Multi-agent coding tool with subagents and persistent teammates"',
        f'  homepage "https://github.com/{REPO}"',
        f'  version "{version}"',
        "",
    ]

    # macOS 平台
    if (DIST_DIR / PLATFORMS["darwin-x86_64"]).exists():
        binary = PLATFORMS["darwin-x86_64"]
        lines += [
            "  on_macos do",
            f'    url "https://github.com/{REPO}/releases/download/v{version}/{binary}"',
            f'    sha256 "{sha256(DIST_DIR / binary)}"',
            "  end",
            "",
        ]

    # Linux 平台
    if (DIST_DIR / PLATFORMS["linux-x86_64"]).exists():
        binary = PLATFORMS["linux-x86_64"]
        lines += [
            "  on_linux do",
            f'    url "https://github.com/{REPO}/releases/download/v{version}/{binary}"',
            f'    sha256 "{sha256(DIST_DIR / binary)}"',
            "  end",
            "",
        ]

    lines += [
        "  def install",
        '    bin.install Dir["myagent-*"].first => "myagent"',
        "  end",
        "",
        "  test do",
        '    system "#{bin}/myagent", "--version"',
        "  end",
        "end",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python generate-formula.py <版本号>", file=sys.stderr)
        sys.exit(1)
    print(generate(sys.argv[1]))
