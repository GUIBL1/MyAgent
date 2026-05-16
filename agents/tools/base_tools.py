#!/usr/bin/env python3
"""
base_tools.py

基础工具实现模块。

对外提供 BaseTools 类，包含 run_shell、read_file、write_file、edit_file 四个工具方法。
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import threading
from pathlib import Path


class BaseTools:
    """基础工具集：Shell 执行、文件读写、编辑。"""

    def __init__(self, workdir: Path, require_confirm_high_risk_command: bool = True, require_confirm_normal_command: bool = True):
        # run_shell 工具执行命令时的用户批准锁，多 agent 并发时，确保同一时间只有一个命令在等待用户批准。
        self._confirmation_lock = threading.RLock()
        # write_file 和 edit_file 工具的文件锁注册表，按文件路径维护 RLock，避免同一文件的并发写入导致数据损坏。
        self._file_lock_registry: dict[str, threading.RLock] = {}

        # 来自.env的控制参数
        self._workdir = workdir
        self._require_confirm_high_risk_command = require_confirm_high_risk_command
        self._require_confirm_normal_command = require_confirm_normal_command

        self._dangerous_snippets: dict[str, list[str]] = {
            "critical": [
                "rm -rf /",
                "rm -rf /*",
                "--no-preserve-root /",
                "shutdown -h now",
                "reboot",
                "init 0",
                "halt",
                "dd if=/dev/zero of=/dev/",
                "mkfs",
                "chmod -r 777 /",
                "chown -r",
                "echo c > /proc/sysrq-trigger",
                "kill -9 1",
                "umount /",
                "mv / /dev/null",
            ],
            "high_risk": [
                "sudo",
                "setenforce 0",
                "kill -9",
                "umount /data",
                "cp -f",
                "curl",
                "wget",
                "| bash",
                "| sh",
                "~/.bashrc",
                "~/.zshrc",
                "~/.profile",
                "~/.ssh/",
                "/etc/",
            ],
        }

        self._critical_patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(r"\brm\s+-rf(?:\s+--no-preserve-root)?\s+/(?:\s|$|\*)", re.IGNORECASE), "rm -rf root directory deletion"),
            (re.compile(r"\bfind\s+/\S*.*-exec\s+rm\b", re.IGNORECASE), "find + rm full disk deletion"),
            (re.compile(r">\s*/dev/(?:sd|nvme|vd|xvd)\S*", re.IGNORECASE), "write data to block device"),
            (re.compile(r"\bdd\s+if=/dev/zero\s+of=/dev/\S+", re.IGNORECASE), "dd overwrite disk"),
            (re.compile(r"\bmkfs(?:\.[\w-]+)?\s+/dev/\S+", re.IGNORECASE), "format device"),
            (re.compile(r"\bchmod\s+-R\s+777\s+/", re.IGNORECASE), "modify root directory permissions"),
            (re.compile(r"\bchown\s+-R\s+\S+\s+/", re.IGNORECASE), "modify root directory ownership"),
            (re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\};\s*:", re.IGNORECASE), "Fork bomb"),
            (re.compile(r"\b(?:shutdown\s+-h\s+now|init\s+0|halt|reboot(?:\s+-f)?)\b", re.IGNORECASE), "shutdown or reboot"),
            (re.compile(r"\becho\s+c\s*>\s*/proc/sysrq-trigger\b", re.IGNORECASE), "trigger kernel panic"),
            (re.compile(r"\bkill\s+-9\s+1\b", re.IGNORECASE), "force kill PID 1"),
            (re.compile(r"\bumount\s+/\b", re.IGNORECASE), "unmount root filesystem"),
            (re.compile(r"\bmv\s+/\s+/dev/null\b", re.IGNORECASE), "move root directory"),
        ]

        self._high_risk_patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(r"\bsudo\b", re.IGNORECASE), "privilege escalation command"),
            (re.compile(r"\bsetenforce\s+0\b", re.IGNORECASE), "disable SELinux"),
            (re.compile(r"\bkill\s+-9\s+\d+\b", re.IGNORECASE), "force kill process"),
            (re.compile(r"\bumount\s+/data\b", re.IGNORECASE), "unmount business data disk"),
            (re.compile(r"\bcp\s+-f\s+\S+\s+/etc/\S*", re.IGNORECASE), "overwrite system configuration file"),
            (re.compile(r"\b(?:curl|wget)\b[^\n|;]*\|\s*(?:bash|sh)\b", re.IGNORECASE), "remote script pipe execution"),
            (re.compile(r"(?:>|>>|tee\s+)(?:\s*)~/(?:\.bashrc|\.zshrc|\.profile|\.ssh/\S*)", re.IGNORECASE), "modify user configuration file"),
            (re.compile(r"(?:>|>>|tee\s+)(?:\s*)/etc/\S+", re.IGNORECASE), "modify system configuration file"),
        ]


    # ======================== public ========================

    def run_shell(
        self,
        command: str,
        timeout: int = 120,
    ) -> str:
        """执行 Shell 命令，按风险等级进行拦截或确认。"""
        if not command.strip():
            return "Error: Empty command."

        risk = self._detect_shell_risk(command)
        if risk and risk[0] == "critical":
            return f"Error: Command blocked at architecture layer (critical risk: {risk[1]})."

        needs_confirmation = self._require_confirm_normal_command
        risk_reason: str | None = None

        if risk and risk[0] == "high_risk":
            needs_confirmation = self._require_confirm_high_risk_command
            risk_reason = risk[1]

        if needs_confirmation and not self._request_user_confirmation(command, risk_reason):
            return "Error: Command execution denied by user."

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self._workdir or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            return output if output else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Timeout ({timeout}s)."
        except Exception as exc:
            return f"Error: {exc}"


    def read_file(
        self,
        path: str, # 文件路径，相对路径（相对于工作区）
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """读取文本文件，支持按起止行返回（闭区间）。"""
        try:
            file_path = self._safe_path(path, self._workdir or Path.cwd())
            content = file_path.read_text(encoding="utf-8")

            normalized_start = self._normalize_line_number("start_line", start_line)
            normalized_end = self._normalize_line_number("end_line", end_line)

            if normalized_start is None and normalized_end is None:
                return content

            lines = content.splitlines()
            total_lines = len(lines)

            start = normalized_start or 1
            end = normalized_end or total_lines

            if end < start:
                return "Error: end_line must be >= start_line."
            if start > total_lines:
                return ""

            end = min(end, total_lines)
            return "\n".join(lines[start - 1 : end])
        except Exception as exc:
            return f"Error: {exc}"


    def write_file(
        self,
        path: str,
        content: str,
    ) -> str:
        """原子写入文本文件，不存在的父目录会自动创建。"""
        try:
            file_path = self._safe_path(path, self._workdir or Path.cwd())
            with self._file_lock_registry.setdefault(str(file_path), threading.RLock()):
                self._atomic_write_text(file_path, content)
            return f"Successfully wrote to {path}."
        except Exception as exc:
            return f"Error: {exc}"


    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> str:
        """在文件中精确替换一次指定文本，并原子落盘。"""
        try:
            file_path = self._safe_path(path, self._workdir or Path.cwd())
            with self._file_lock_registry.setdefault(str(file_path), threading.RLock()):
                content = file_path.read_text(encoding="utf-8")
                if old_text not in content:
                    return f"Error: Old text not found in {path}."
                updated = content.replace(old_text, new_text, 1)
                self._atomic_write_text(file_path, updated)
            return f"Successfully edited {path}."
        except Exception as exc:
            return f"Error: {exc}"


    # ======================== private ========================

    @staticmethod
    def _safe_path(path: str, workdir: Path) -> Path:
        """将相对路径解析到工作区，并阻止路径逃逸。"""
        path = (workdir / path).resolve()
        if not path.is_relative_to(workdir):
            raise ValueError(f"Path {path} escapes workspace {workdir}.")
        return path

    def _detect_shell_risk(self, command: str) -> tuple[str, str] | None:
        """检测命令风险等级：先匹配快速片段，再匹配正则模式。"""
        normalized = " ".join(command.strip().lower().split())

        for snippet in self._dangerous_snippets["critical"]:
            if snippet in normalized:
                return "critical", f"Matched critical snippet: {snippet}"

        for pattern, reason in self._critical_patterns:
            if pattern.search(command):
                return "critical", reason

        for snippet in self._dangerous_snippets["high_risk"]:
            if snippet in normalized:
                return "high_risk", f"Matched high-risk snippet: {snippet}"

        for pattern, reason in self._high_risk_patterns:
            if pattern.search(command):
                return "high_risk", reason

        return None

    def _request_user_confirmation(self, command: str, risk_reason: str | None = None) -> bool:
        """阻塞式请求用户批准命令执行，返回是否同意执行。"""
        with self._confirmation_lock:
            print(f"Approve shell command?:\n{command}")
            if risk_reason:
                print(f"Warning:\n{risk_reason}.")

            while True:
                try:
                    choice = input("Choose [y/n]: ").strip().lower()
                except EOFError:
                    return False

                if choice == "y":
                    return True
                if choice == "n":
                    return False

                print("Invalid choice, please enter y or n.")

    @staticmethod
    def _normalize_line_number(name: str, value: int | None) -> int | None:
        """校验并规范化行号输入。"""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
        if value < 1:
            raise ValueError(f"{name} must be >= 1.")
        return value

    @staticmethod
    def _atomic_write_text(file_path: Path, content: str) -> None:
        """通过临时文件 + 原子替换落盘，避免半写入状态。"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=file_path.parent,
                delete=False,
            ) as temp_file:
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)

            if file_path.exists():
                current_mode = stat.S_IMODE(file_path.stat().st_mode)
                os.chmod(temp_path, current_mode)

            os.replace(temp_path, file_path)
            # fsync 目录，保证 rename 元数据落盘
            try:
                dir_fd = os.open(str(file_path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
