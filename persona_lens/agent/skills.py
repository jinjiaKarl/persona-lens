"""Skill loader and use_skill tool for persona-lens agent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from agents import RunContextWrapper, function_tool

from persona_lens.agent.context import AgentContext

# ── Directories ──────────────────────────────────────────────────────────────

_BUILTIN_DIR = Path(__file__).parent.parent / "skills"
_USER_DIR = Path.home() / ".persona-lens" / "skills"


# ── Skill parsing ─────────────────────────────────────────────────────────────

def _parse_skill_md(path: Path) -> tuple[str, dict[str, Any], str]:
    """Return (name, frontmatter_dict, body) from a SKILL.md file."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not match:
        return path.parent.name, {}, text
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        meta = {}
    body = match.group(2).strip()
    name = meta.get("name") or path.parent.name
    return name, meta, body


# ── Registry ──────────────────────────────────────────────────────────────────

def load_skills(
    builtin_dir: Path | None = None,
    user_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan directories for SKILL.md files and return registry dict."""
    if builtin_dir is None:
        builtin_dir = _BUILTIN_DIR
    # user_dir=None means skip user directory (no replacement with _USER_DIR here)

    registry: dict[str, dict[str, Any]] = {}

    for base in (builtin_dir, user_dir):
        if base is None or not base.exists():
            continue
        for skill_md in sorted(base.glob("*/SKILL.md")):
            name, meta, body = _parse_skill_md(skill_md)
            if not meta.get("description"):
                continue
            registry[name] = {
                "description": meta["description"],
                "body": body,
                "path": skill_md,
            }

    return registry


_SKILLS: dict[str, dict[str, Any]] = load_skills(user_dir=_USER_DIR)


def _skill_list() -> str:
    if not _SKILLS:
        return "(none)"
    return "\n".join(f"- {name}: {s['description']}" for name, s in _SKILLS.items())


# ── Tool ──────────────────────────────────────────────────────────────────────

@function_tool
def use_skill(ctx: RunContextWrapper[AgentContext], command: str) -> str:
    """Invoke a skill by name to follow specialized output or analysis instructions.

Available skills:
{skill_list}

Args:
    command: skill name to invoke (e.g. "kol-report")
"""
    skill = _SKILLS.get(command)
    if not skill:
        available = ", ".join(_SKILLS) or "none"
        return f"Skill '{command}' not found. Available skills: {available}"
    return skill["body"]


# Patch the description with the live skill list at import time.
use_skill.description = use_skill.description.format(skill_list=_skill_list())
