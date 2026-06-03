"""session_manager.py

会话存储管理模块。

管理双通道持久化：
- transcript.jsonl：完整事件转录（所有 StreamEvent，供前端回放）
- context.jsonl：LLM 上下文消息（Anthropic API 格式，仅从 CONTEXT_ENTRY 提取）

支持 turn 级回退 (Rewind)、会话列表和切换。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionManager:
    """会话存储管理器。"""

    def __init__(self, sessions_dir: Path | None):
        self._sessions_dir = sessions_dir
        self._session_id: str | None = None
        self._session_dir: Path | None = None
        self._transcript_path: Path | None = None
        self._context_path: Path | None = None
        self._current_turn: int = 0
        self._current_seq: int = 0

    # ======================== public ========================

    # ---- 会话生命周期 ----

    def new_session(self) -> str:
        """创建新会话目录和空文件，返回 session_id。"""
        sid = uuid.uuid4().hex[:12]
        self._session_id = sid
        self._session_dir = self._sessions_dir / sid if self._sessions_dir else None
        self._current_turn = 0
        self._current_seq = 0

        if self._session_dir:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._transcript_path = self._session_dir / "transcript.jsonl"
            self._context_path = self._session_dir / "context.jsonl"
            self._transcript_path.touch()
            self._context_path.touch()

        return sid

    def switch_session(self, session_id: str) -> None:
        """切换到已有会话，从 transcript 恢复当前 turn。"""
        self._session_id = session_id
        self._session_dir = self._sessions_dir / session_id if self._sessions_dir else None
        self._current_seq = 0
        if self._session_dir:
            self._transcript_path = self._session_dir / "transcript.jsonl"
            self._context_path = self._session_dir / "context.jsonl"
            self._current_turn = self.count_turns()
        else:
            self._current_turn = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def current_turn(self) -> int:
        return self._current_turn

    # ---- 写入 ----

    def write_transcript(self, entry: dict[str, Any]) -> None:
        """追加一行事件到 transcript.jsonl。"""
        if not self._transcript_path:
            return
        self._write_jsonl(self._transcript_path, entry)

    def write_context(self, message: dict[str, Any]) -> None:
        """追加一条 Anthropic API 格式消息到 context.jsonl。"""
        if not self._context_path:
            return
        self._write_jsonl(self._context_path, message)

    def save_context_full(self, messages: list[dict[str, Any]]) -> None:
        """覆写 context.jsonl（压缩后使用）。"""
        if not self._context_path:
            return
        self._write_jsonl(self._context_path, messages, mode="w")

    def apply_context_patch(self, patches: list[dict[str, Any]]) -> None:
        """将 context_patch 应用到 transcript，修正指定逆序位置的 context_entry。

        patches 格式: [{"rev_msg_idx": N, "part_idx": N, "new_entry": {...}}, ...]
        rev_msg_idx=0 表示 transcript 中最后一条 context_entry，1 表示倒数第二条，以此类推。
        """
        if not self._transcript_path:
            return

        transcript = self._read_jsonl(self._transcript_path)

        for p in patches:
            rev_msg_idx = p["rev_msg_idx"]
            part_idx = p["part_idx"]
            new_entry = p["new_entry"]

            count = 0
            for i in range(len(transcript) - 1, -1, -1):
                entry = transcript[i]
                if entry.get("type") != "context_entry":
                    continue
                if count == rev_msg_idx:
                    ce = json.loads(entry["content"])
                    if isinstance(ce.get("content"), list) and part_idx < len(ce["content"]):
                        ce["content"][part_idx] = new_entry["content"][0]
                    entry["content"] = json.dumps(ce, ensure_ascii=False)
                    break
                count += 1

        self._write_jsonl(self._transcript_path, transcript, mode="w")

    # ---- 读取 ----

    def load_context(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """从 context.jsonl 读取完整 messages 列表。

        如果传了 session_id，先切换到该会话。
        """
        if session_id:
            self.switch_session(session_id)
        if not self._context_path:
            return []
        return self._read_jsonl(self._context_path)

    def load_transcript(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """从 transcript.jsonl 读取完整事件列表。"""
        if session_id:
            self.switch_session(session_id)
        if not self._transcript_path:
            return []
        return self._read_jsonl(self._transcript_path)

    # ---- Turn 管理 ----

    def advance_turn(self) -> None:
        """当前 turn 结束，turn+1，seq 归零。"""
        self._current_turn += 1
        self._current_seq = 0

    def next_seq(self) -> int:
        """返回当前 turn 内的下一个 seq 并自增。"""
        n = self._current_seq
        self._current_seq += 1
        return n

    def count_turns(self, session_id: str | None = None) -> int:
        """统计 transcript 中的用户 turn 数量。不切换会话。"""
        transcript_path = self._resolve_transcript_path(session_id)
        if not transcript_path:
            return 0
        turns: set[int] = set()
        for entry in self._read_jsonl(transcript_path):
            t = entry.get("turn")
            if t is not None:
                turns.add(t)
        return len(turns)

    # ---- Rewind ----

    def rewind_to_turn(self, turn_index: int) -> list[dict[str, Any]]:
        """截断 transcript 到指定 turn，重建 context，返回 messages。"""
        if not self._transcript_path:
            return []

        transcript = self._read_jsonl(self._transcript_path)

        # 逆序找到 turn_index 的 user_message，保留其之前的所有行
        cutoff = len(transcript)
        for i in range(len(transcript) - 1, -1, -1):
            if transcript[i].get("type") == "user_message" and transcript[i].get("turn") == turn_index:
                cutoff = i
                break

        kept = transcript[:cutoff]

        self._write_jsonl(self._transcript_path, kept, mode="w")

        context = self._rebuild_context(kept)
        self._write_jsonl(self._context_path, context, mode="w")

        self._current_turn = turn_index
        self._current_seq = 0

        return context

    # ---- 会话列表 ----

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话目录，按更新时间倒序。"""
        if not self._sessions_dir:
            return []
        result: list[dict[str, Any]] = []
        try:
            for d in sorted(self._sessions_dir.iterdir(), reverse=True):
                if not d.is_dir():
                    continue
                transcript_path = d / "transcript.jsonl"
                if not transcript_path.exists():
                    continue

                stat = transcript_path.stat()
                title, turns = self._extract_title_and_turns(transcript_path)

                result.append({
                    "session_id": d.name,
                    "title": title,
                    "turns": turns,
                    "created_at": self._fmt_timestamp(stat.st_ctime),
                    "updated_at": self._fmt_timestamp(stat.st_mtime),
                })
        except OSError:
            return []

        result.sort(key=lambda s: s["updated_at"], reverse=True)
        return result

    # ======================== private ========================

    def _rebuild_context(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """从 transcript 重建 context。

        逆序找到最后一个 auto_compact 边界，从边界后提取 CONTEXT_ENTRY。
        CONTEXT_ENTRY 已被 apply_context_patch 实时修正，无需再处理 context_patch。
        """
        start = 0
        for i in range(len(transcript) - 1, -1, -1):
            if transcript[i].get("type") == "auto_compact_done":
                start = i + 1
                break

        context: list[dict[str, Any]] = []
        for entry in transcript[start:]:
            if entry.get("type") == "context_entry":
                try:
                    context.append(json.loads(entry["content"]))
                except json.JSONDecodeError:
                    pass

        return context

    def _resolve_transcript_path(self, session_id: str | None) -> Path | None:
        """根据 session_id 解析 transcript 路径，不切换会话。"""
        if session_id and self._sessions_dir:
            return self._sessions_dir / session_id / "transcript.jsonl"
        return self._transcript_path

    @staticmethod
    def _extract_title_and_turns(filepath: Path) -> tuple[str, int]:
        """从文件头和尾提取：title=首条 user_message 前 80 字，turns=最后一条 entry 的 turn+1。"""
        title = ""
        max_turn = 0
        try:
            with filepath.open(encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return "", 0

        # 正向扫第一条 user_message → title
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "user_message":
                title = entry.get("content", "")[:80]
                break

        # 逆序扫最后一条带 turn 的 → max_turn
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = entry.get("turn")
            if t is not None:
                max_turn = t + 1
                break

        return title, max_turn

    @staticmethod
    def _read_jsonl(filepath: Path) -> list[dict[str, Any]]:
        """读取 JSONL 文件，返回 dict 列表。"""
        entries: list[dict[str, Any]] = []
        try:
            with filepath.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return entries

    @staticmethod
    def _write_jsonl(filepath: Path, entry: dict[str, Any] | list[dict[str, Any]], mode: str = "a") -> None:
        """写入 JSONL 文件。"""
        entries = entry if isinstance(entry, list) else [entry]
        try:
            with filepath.open(mode, encoding="utf-8") as f:
                for item in entries:
                    f.write(json.dumps(item, default=str, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"[session_manager] write failed: {exc}")

    @staticmethod
    def _fmt_timestamp(ts: float) -> str:
        """将 POSIX 时间戳格式化为 ISO 字符串。"""
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
