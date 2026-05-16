#!/usr/bin/env python3
"""
skill_manager.py

skill 管理模块。

扫描 `WORKDIR/.MyAgent/skills/**/SKILL.md`，并提供两类能力：
1. skill_descriptions()：返回技能简介，用于系统提示词。
2. load_skill(skill_name)：按名称加载完整技能正文。
"""

from __future__ import annotations

import re
from pathlib import Path


class SkillManager:
    """从 skills 目录发现并加载 skill 内容。"""

    def __init__(self, skills_dir: Path):
        # 技能数据结构：{ skill_name: { "meta": {"name": "...", description: "..."}, "body": "..." } }
        self._skills: dict[str, dict[str, str | dict[str, str]]] = {}

        if skills_dir.exists():
            for skill_file_dir in sorted(skills_dir.rglob("SKILL.md")):
                try:
                    text = skill_file_dir.read_text()
                except Exception as exc:
                    print(f"[SkillManager]: Unreadable '{skill_file_dir}' with error: {exc}")
                    continue

                try:
                    metadata, body = self._parse_skill(text)
                except Exception as exc:
                    print(f"[SkillManager]: Invalid skill format in '{skill_file_dir}' with error: {exc}")
                    continue

                # skill 名称优先使用 metadata 中的 name 字段，否则使用目录名
                skill_name = metadata.get("name", skill_file_dir.parent.name)

                if skill_name in self._skills.keys():
                    print(f"[SkillManager]:Skill '{skill_name}' of '{skill_file_dir}' overwrite previous skill with the same name.")
                self._skills[skill_name] = {"meta": metadata, "body": body}

    # ======================== public ========================

    def skill_descriptions(self) -> str:
        """返回系统提示词可用的技能简介列表。"""
        if not self._skills:
            return "(no skills)."
        return "Usable skills(name of skill: description of skill):\n" + "\n".join(
            f"{skill_name}: {skill['meta'].get('description', '-')}"
            for skill_name, skill in self._skills.items()
        )


    def load_skill(self, skill_name: str) -> str:
        """按技能名加载完整正文。"""
        skill = self._skills.get(skill_name)
        if not skill:
            available = ", ".join(self._skills.keys())
            return f"Error: Unknown skill '{skill_name}'. Available: {available}."
        return f"<skill>\nname: {skill_name}.\n{skill['body']}\n</skill>"

    # ======================== private ========================

    def _parse_skill(self, text: str) -> tuple[dict[str, str], str]:
        """解析 SKILL.md 的元数据与正文。"""
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            raise ValueError("SKILL.md must start with YAML-like metadata block enclosed by ---.")

        metadata: dict[str, str] = {}
        for line in match.group(1).strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        body = match.group(2).strip()
        return metadata, body
