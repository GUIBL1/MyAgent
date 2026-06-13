# Homebrew Formula for MyAgent
# ==============================
#
# 安装方式：
#   brew tap GUIBL1/MyAgent   # 如果 formula 放在主仓库
#   brew install myagent
#
# 或者直接引用 GitHub Release 中的 formula：
#   brew install https://github.com/GUIBL1/MyAgent/releases/latest/download/formula.rb
#
# 此文件由 CI 自动生成（scripts/generate-formula.py），
# 也可手动放到 homebrew-tap 仓库中供 Homebrew 索引。

class Myagent < Formula
  desc "Multi-agent coding tool with subagents and persistent teammates"
  homepage "https://github.com/GUIBL1/MyAgent"
  version "0.1.0"

  on_macos do
    url "https://github.com/GUIBL1/MyAgent/releases/download/v0.1.0/myagent-darwin-x86_64"
    sha256 "PLACEHOLDER"  # CI 会自动替换
  end

  on_linux do
    url "https://github.com/GUIBL1/MyAgent/releases/download/v0.1.0/myagent-linux-x86_64"
    sha256 "PLACEHOLDER"  # CI 会自动替换
  end

  def install
    bin.install Dir["myagent-*"].first => "myagent"
  end

  test do
    system "#{bin}/myagent", "--version"
  end
end
