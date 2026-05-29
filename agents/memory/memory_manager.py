#!/usr/bin/env python3
"""
memory_manager.py

记忆管理器 — agent 写/查记忆的唯一入口。

职责：
1. 管理 MEMORY.md（短期记忆，注入 system prompt）
2. 管理 Chroma（向量数据库，长期记忆 RAG）
3. 启动时检查双阈值，触发记忆整理
4. 提供 write_memory / recall_memory 工具接口
"""

from __future__ import annotations

import atexit
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

class MemoryManager:
    """记忆管理器 — agent 写/查记忆的唯一入口。"""

    def __init__(
        self,
        *,
        embed_base_url: str,
        embed_auth_token: str,
        embed_model: str,
        expand_client: Any,
        expand_model: str,
        rerank_client: Any,
        rerank_model: str,
        synthesize_client: Any,
        synthesize_model: str,
        memory_enabled: bool,
        memory_dir: Path,
        consolidation_interval_days: int,
        max_memory_chars: int,
        forgetting_days: int,
        forgetting_interval_days: int,
        max_vector_records: int,
        max_rag_candidates: int,
        expand_max_output_tokens: int,
        rerank_max_output_tokens: int,
        synthesize_max_output_tokens: int,
    ):
        self._embed_base_url = embed_base_url
        self._embed_auth_token = embed_auth_token
        self._embed_model = embed_model
        self._expand_client = expand_client
        self._expand_model = expand_model
        self._rerank_client = rerank_client
        self._rerank_model = rerank_model
        self._synthesize_client = synthesize_client
        self._synthesize_model = synthesize_model
        self._memory_enabled = memory_enabled
        self._expand_max_output_tokens = expand_max_output_tokens
        self._rerank_max_output_tokens = rerank_max_output_tokens
        self._synthesize_max_output_tokens = synthesize_max_output_tokens
        self._memory_dir = memory_dir
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        self._consolidation_interval_days = consolidation_interval_days
        self._max_memory_chars = max_memory_chars
        self._forgetting_days = forgetting_days
        self._forgetting_interval_days = forgetting_interval_days
        self._max_vector_records = max_vector_records
        self._max_rag_candidates = max_rag_candidates

        self._memory_md_path = self._memory_dir / "MEMORY.md"
        self._config_path = self._memory_dir / "memory_config.json"

        # 确保 MEMORY.md 存在
        if not self._memory_md_path.exists():
            self._memory_md_path.write_text(
                "# SHORT-TERM MEMORY\n"
                "# Appended via the write_memory tool\n"
                "# Periodically categorized and cleared by a grooming LLM, then archived to the vector database\n\n",
            encoding="utf-8",
        )

        # 确保 memory_config.json 存在且含必要字段
        try:
            config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config_data = {}
        config_data.setdefault("last_consolidation", datetime.now(timezone.utc).isoformat())
        config_data.setdefault("last_forgetting", datetime.now(timezone.utc).isoformat())
        self._config_path.write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._chroma_client = None  # Chroma PersistentClient
        self._collection = None     # Chroma Collection

        if self._memory_enabled:
            self._init_database()
            atexit.register(self._shutdown)
            self._check_forget()
            self._check_consolidation()

    # ======================== public ========================
    def get_tool_schemas(self) -> list[dict]:
        """返回 memory 工具 schema 列表。"""
        if not self._memory_enabled:
            return []
        return [
            {
                "name": "write_memory",
                "description":
                    "Write a natural-language memory entry into short-term memory (MEMORY.md). "
                    "Content is appended with an automatic date tag. "
                    "No structuring needed — write as if explaining to a colleague. "
                    "Use this to remember: architectural conventions, bug fix experiences, "
                    "user preferences, design decisions and their rationale, or module relationships "
                    "that are implicit and hard to discover from code alone. "
                    "Short-term memories are periodically consolidated into long-term vector storage.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Natural language memory content. Write freely — no structuring needed.",
                        },
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "recall_memory",
                "description":
                    "Search long-term memory (vector database) for memories relevant to your query. "
                    "Returns a synthesized answer via RAG pipeline (query expansion → retrieval → rerank → synthesis). "
                    "Use this when you need to check: past bug fixes, historical design decisions, "
                    "architectural conventions, user preferences, or anything that may have been recorded in previous sessions. "
                    "Short-term memories (in MEMORY.md) are already in your context — no need to search them.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for finding relevant long-term memories.",
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    def get_tool_handlers(self) -> dict[str, Any]:
        """返回 tool_name → handler 映射。"""
        if not self._memory_enabled:
            return {}
        return {
            "write_memory": lambda **kw: self.write_memory(content=kw["content"]),
            "recall_memory": lambda **kw: self.recall_memory(query=kw["query"]),
        }

    def build_memory_prompt(self) -> str:
        """构建注入 system prompt 的记忆片段（使用规范 + 短期记忆快照），记忆未启用时返回空。"""
        if not self._memory_enabled:
            return ""

        parts: list[str] = []
        # 记忆使用规范
        parts.append(
            "## Memory Usage\n"
            "- write_memory: Record architectural conventions, bug fixes, "
            "user preferences, design decisions, or implicit module relationships.\n"
            "- recall_memory: Search long-term memory before modifying a module "
            "with known pitfalls, or when you need historical context.\n"
            "- Do NOT write memories for facts already obvious from code."
        )
        # 短期记忆快照
        try:
            snapshot = self._memory_md_path.read_text(encoding="utf-8")
        except OSError:
            snapshot = ""
        core = "\n".join(
            line for line in snapshot.splitlines()
            if self._is_memory_content(line)
        ).strip()
        if core:
            parts.append(
                "## Short-Term Memory (current snapshot)\n"
                "These are recent memories. Use recall_memory to search older ones.\n\n"
                + core
            )
        return "\n\n".join(parts)

    def write_memory(self, content: str) -> str:
        """追加一段自然语言记忆到 MEMORY.md。"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n## {timestamp}\n{content.strip()}\n"
            with self._memory_md_path.open("a", encoding="utf-8") as f:
                f.write(entry)
            return "Memory written."
        except OSError as exc:
            return f"Memory write failed: {exc}"

    def recall_memory(self, query: str) -> str:
        """RAG 检索长期记忆：query 扩展 → 向量检索 → 重排序 → 合成 LLM。"""
        if not self._collection:
            return "No relevant memory."

        try:
            # Step 1: query 扩展 — 让 LLM 生成多条变体查询
            expanded = self._expand_query(query)

            # Step 2: 多路检索 — 每条变体独立检索
            all_candidates: dict[str, tuple[str, dict, float]] = {}  # id → (doc, meta, distance)
            for q in expanded:
                embedding = self._embed(q)
                if not embedding:
                    continue
                result = self._collection.query(
                    query_embeddings=[embedding],
                    n_results=self._max_rag_candidates,
                )
                if result and result.get("ids"):
                    for i, id in enumerate(result["ids"][0]):
                        if id not in all_candidates:
                            doc = result["documents"][0][i] if result.get("documents") else ""
                            meta = result["metadatas"][0][i] if result.get("metadatas") else {}
                            dist = result["distances"][0][i] if result.get("distances") else 0.0
                            all_candidates[id] = (doc, meta, dist)

            if not all_candidates:
                return "No relevant memory."

            # Step 3: 重排序 — LLM 对候选逐条打分
            ranked = self._rerank(query, all_candidates)

            # Step 4: 合成 — top-K 送合成 LLM
            top = ranked[: self._max_rag_candidates]
            result = self._synthesize(query, top)

            # 更新命中记忆的访问元数据
            hit_ids = [id for id, _ in top]
            if hit_ids:
                self._update_access_metadata(hit_ids)

            return result

        except Exception as exc:
            return f"[Memory] recall failed: {exc}"

    # ======================== private: memory recall tools ========================
    def _update_access_metadata(self, hit_ids: list[str]) -> None:
        """更新命中记忆的 last_accessed_at 和 access_count。"""
        if not self._collection:
            return
        try:
            existing = self._collection.get(ids=hit_ids)
            if not existing or not existing.get("ids"):
                return
            now_str = datetime.now(timezone.utc).isoformat()
            for i, id in enumerate(existing["ids"]):
                meta = (existing.get("metadatas") or [{}])[i] or {}
                meta["last_accessed_at"] = now_str
                meta["access_count"] = meta.get("access_count", 0) + 1
                try:
                    self._collection.update(ids=[id], metadatas=[meta])
                except Exception:
                    pass
        except Exception as exc:
            print(f"[Memory] access update failed: {exc}")

    def _embed(self, text: str) -> list[float] | None:
        """HTTP POST 调用 embedding，含退避重试。"""
        import time as _time
        max_retries = 10
        for attempt in range(max_retries):
            try:
                import httpx
                resp = httpx.post(
                    f"{self._embed_base_url.rstrip('/')}/embeddings",
                    json={"model": self._embed_model, "input": text},
                    headers={"Authorization": f"Bearer {self._embed_auth_token}"},
                    timeout=60,
                )
                if resp.status_code == 429:
                    _time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
            except Exception as exc:
                if attempt == max_retries - 1:
                    print(f"[Memory] embedding failed after {max_retries} retries: {exc}")
                else:
                    _time.sleep(2 ** attempt)
        print(f"[Memory] embedding failed after {max_retries} retries.")
        return None

    def _expand_query(self, query: str) -> list[str]:
        """LLM 生成多条变体查询，覆盖不同表述角度。"""
        try:
            expanded_system_prompt = (
                "You are a retrieval query expander. "
                "Task: Generate 3-10 differently phrased search queries based on the user's query."
                "Requirements: One per line; no numbering, no quotes, no explanations; output queries only."
                "Coverage: synonym rewrite, abstraction/generalization, keyword combination."
                "Preserve core entities/time/place/product names/code snippets; do not fabricate new facts."
                "Match the output language to the original query."
            )
            with self._expand_client.messages.stream(
                model=self._expand_model,
                system=expanded_system_prompt,
                messages=[{"role": "user", "content": query}],
                max_tokens=self._expand_max_output_tokens,
            ) as stream:
                response = stream.get_final_message()
            text = "".join(
                getattr(block, "text", "")
                for block in response.content
                if hasattr(block, "text")
            )
            variants = [q.strip() for q in text.strip().splitlines() if q.strip()]
            # 原始 query 始终参与
            if query not in variants:
                variants.insert(0, query)
            return variants
        except Exception:
            return [query]

    def _rerank(self, query: str, candidates: dict[str, tuple[str, dict, float]]) -> list[tuple[str, str]]:
        """LLM 对候选记忆逐条打分排序。"""
        lines = []
        for (id, (doc, meta, dist)) in candidates.items():
            access_count = meta.get("access_count", 0) if meta else 0
            lines.append(
                f"memory id:{id}.\n"
                f"access count:{access_count}. distance: {dist:.4f}.\n"
                f"content: {doc}"
            )

        rerank_system_prompt = (
            "You are a retrieval re-ranking assistant.\n"
            "Task: Score candidate memories against the query and return a descending order.\n"
            "Fields: access count — past access count of the memory; distance — vector distance between query and memory (lower = closer); content — memory content.\n"
            "Scoring factors (importance descending): semantic match > distance > access_count.\n"
            "Return: one memory id per line, ordered by score descending, no prefixes, no explanations."
        )
        prompt = (
            f"Original query: {query}\n\n"
            f"Candidate memories:\n" + "\n\n".join(lines)
        )
        try:
            with self._rerank_client.messages.stream(
                model=self._rerank_model,
                system=rerank_system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._rerank_max_output_tokens,
            ) as stream:
                response = stream.get_final_message()
            text = "".join(
                getattr(block, "text", "")
                for block in response.content if hasattr(block, "text")
            )
            order: list[tuple[str, str]] = []
            for line in text.strip().splitlines():
                memory_id = line.strip()
                if memory_id in candidates:
                    order.append((memory_id, candidates[memory_id][0]))
            if order:
                return order
        except Exception:
            pass
        # 降级：按原始顺序返回
        return [(id, doc) for id, (doc, _, _) in candidates.items()]

    def _synthesize(self, query: str, top_candidates: list[tuple[str, str]]) -> str:
        """合成 LLM 整合 top-K 结果。"""
        if not top_candidates:
            return "No relevant memory."

        fragments = ["Memory fragments (format: [index]: content):"]
        for i, (_, doc) in enumerate(top_candidates):
            fragments.append(f"[{i}]: {doc}")

        synthesize_system_prompt = (
            "You are a memory retrieval synthesizer.\n"
            "Task: Synthesize the memory fragments to answer the query using only the provided content.\n"
            "Rules:\n"
            "- If fragments contradict, prefer the one with the smaller index.\n"
            "- Match the response language to the query language.\n"
            "- Never fabricate content not present in the fragments.\n"
            "- Be concise."
        )
        prompt = f"Original query: {query}\n\n" + "\n\n".join(fragments)

        try:
            with self._synthesize_client.messages.stream(
                model=self._synthesize_model,
                system=synthesize_system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._synthesize_max_output_tokens,
            ) as stream:
                response = stream.get_final_message()
            text_parts = [
                getattr(block, "text", "")
                for block in response.content if hasattr(block, "text")
            ]
            return "\n".join(text_parts).strip() or "No relevant memory."
        except Exception as exc:
            print(f"[Memory] synthesis failed: {exc}")
            return "Memory retrieval results:\n" + "\n\n".join(
                f"{doc}" for _, doc in top_candidates
            )
    # ======================== private: init ========================
    def _init_database(self) -> None:
        """初始化 Chroma 连接。"""
        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=str(self._memory_dir / "vectors"))
            existing = [c.name for c in self._chroma_client.list_collections()]
            if "longterm_memories" not in existing:
                self._collection = self._chroma_client.create_collection(
                    name="longterm_memories",
                    metadata={"description": "Long-Term Semantic Memories"},
                )
            else:
                self._collection = self._chroma_client.get_collection(
                    name="longterm_memories"
                )
        except Exception as exc:
            print(f"[Memory] Chroma init failed: {exc}")

    # ======================== private: consolidation ========================
    def _check_consolidation(self) -> None:
        """检查双阈值是否触发整理。"""
        config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
        last_str = config_data.get("last_consolidation", "")

        need_consolidation = False

        if last_str:
            try:
                last = datetime.fromisoformat(last_str)
                days_elapsed = (datetime.now(timezone.utc) - last).days
                if days_elapsed >= self._consolidation_interval_days:
                    need_consolidation = True
            except ValueError:
                need_consolidation = True

        if not need_consolidation:
            try:
                char_count = len(self._memory_md_path.read_text(encoding="utf-8"))
                if char_count >= self._max_memory_chars:
                    need_consolidation = True
            except OSError:
                pass

        if need_consolidation:
            self._consolidate()

    def _consolidate(self) -> None:
        """整理流程：embed 每条记忆 → 写入 Chroma → 清空 MEMORY.md。"""
        print("[Memory] starting consolidation...")
        try:
            memory_text = self._memory_md_path.read_text(encoding="utf-8")
        except OSError:
            return

        entries = self._split_entries(memory_text)
        if not entries:
            return

        now_ts = datetime.now(timezone.utc)
        archived = 0

        for i, entry in enumerate(entries):
            content = entry.strip()
            if not content:
                continue
            # 去除 ## 日期 标题行（保留原文正文）
            # 格式: ## 2026-05-21 10:30\n正文...
            body = content.split("\n", 1)[1] if "\n" in content else content
            embedding = self._embed(body)
            if not embedding:
                continue
            mem_id = f"mem_{now_ts.strftime('%Y%m%d_%H%M%S')}_{i}"
            metadata = {
                "created_at": now_ts.isoformat(),
                "last_accessed_at": now_ts.isoformat(),
                "access_count": 0,
            }
            try:
                self._collection.add(
                    ids=[mem_id],
                    documents=[body],
                    embeddings=[embedding],
                    metadatas=[metadata],
                )
                archived += 1
            except Exception as exc:
                print(f"[Memory] Chroma insert failed: {exc}")

        if archived == 0:
            print("[Memory] consolidation aborted: no entries embedded — nothing was archived, MEMORY.md preserved.")
            return

        # 清空 MEMORY.md
        self._memory_md_path.write_text(
            "# SHORT-TERM MEMORY\n"
            "# Appended via the write_memory tool\n"
            "# Periodically categorized and cleared by a grooming LLM, then archived to the vector database\n\n",
            encoding="utf-8",
        )

        # 更新整理时间戳
        try:
            config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
            config_data["last_consolidation"] = datetime.now(timezone.utc).isoformat()
            self._config_path.write_text(
                json.dumps(config_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

        print(f"[Memory] consolidation complete: {len(entries)} entries → {archived} archived.")

    def _split_entries(self, text: str) -> list[str]:
        """按 write_memory 格式（## YYYY-MM-DD HH:MM）分割为记忆单元。"""
        entries: list[str] = []
        current: list[str] = []
        ts_pattern = re.compile(r"^## \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        for line in text.splitlines():
            if ts_pattern.match(line):
                if current:
                    entries.append("\n".join(current).strip())
                current = [line]
            elif current:
                current.append(line)
        if current:
            entries.append("\n".join(current).strip())
        return entries

    # ======================== private: forgetting ========================
    def _check_forget(self) -> None:
        """检查遗忘时间阈值是否触发，如触发则执行遗忘策略。"""
        config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
        last_str = config_data.get("last_forgetting", "")
        if not last_str:
            self._forget()  # 无遗忘记录时主动触发遗忘，确保新部署的系统也能定期清理过期记忆
            return
        try:
            last = datetime.fromisoformat(last_str)
            if (datetime.now(timezone.utc) - last).days >= self._forgetting_interval_days:
                self._forget()
        except ValueError:
            self._forget()  # 日期损坏时主动触发遗忘

    def _forget(self) -> None:
        """执行遗忘策略。自然淘汰始终执行，容量淘汰仅在超限时执行。"""
        if not self._collection:
            return

        print("[Memory] starting forgetting...")
        now_ts = datetime.now(timezone.utc)

        # 拉取一次全量记录，自然淘汰和容量淘汰共享
        try:
            all_records = self._collection.get()
            if all_records and all_records.get("ids"):
                ids = all_records["ids"]
                metadatas = all_records.get("metadatas", []) or []

                # 自然淘汰：access_count < 2 且超过 forgetting_days
                natural_deletes: list[str] = []
                for i, id in enumerate(ids):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    access_count = meta.get("access_count", 0)
                    last_access_str = meta.get("last_accessed_at", "")
                    try:
                        last_access = datetime.fromisoformat(last_access_str)
                        days_since = (now_ts - last_access).days
                    except (ValueError, TypeError):
                        days_since = 365  # 损坏日期视为一年未访问
                    if access_count < 2 and days_since > self._forgetting_days:
                        natural_deletes.append(id)
                if natural_deletes:
                    self._collection.delete(ids=natural_deletes)
                    print(f"[Memory] natural forgetting: {len(natural_deletes)} deleted.")

                # 容量淘汰：自然淘汰后仍超限时，淘汰分数最低的 (访问次数 / 未访问天数)
                retained = [id for id in ids if id not in natural_deletes]
                if len(retained) > self._max_vector_records:
                    scored: list[tuple[str, float]] = []
                    for i, id in enumerate(ids):
                        if id in natural_deletes:
                            continue
                        meta = metadatas[i] if i < len(metadatas) else {}
                        access_count = meta.get("access_count", 0)
                        last_access_str = meta.get("last_accessed_at", "")
                        try:
                            last_access = datetime.fromisoformat(last_access_str)
                            days_since = max((now_ts - last_access).days, 1)
                        except (ValueError, TypeError):
                            days_since = 365  # 损坏日期视为一年未访问
                        scored.append((id, access_count / days_since))
                    scored.sort(key=lambda x: x[1])
                    overflow = len(scored) - self._max_vector_records
                    if overflow > 0:
                        to_delete = [s[0] for s in scored[:overflow]]
                        self._collection.delete(ids=to_delete)
                        print(f"[Memory] capacity forgetting: {len(to_delete)} deleted.")
        except Exception as exc:
            print(f"[Memory] forgetting failed: {exc}")

        # 记录遗忘时间戳
        try:
            config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
            config_data["last_forgetting"] = datetime.now(timezone.utc).isoformat()
            self._config_path.write_text(
                json.dumps(config_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _is_memory_content(line: str) -> bool:
        """## 时间戳行或正文行保留，# 注释行排除。"""
        return not (line.startswith("#") and not line.startswith("## "))

    # ======================== private: cleanup ========================
    def _shutdown(self) -> None:
        """关闭 Chroma 连接。"""
        try:
            self._chroma_client = None
            self._collection = None
        except Exception:
            pass
