# Agent Skills System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a SKILL.md-based skills system to the persona-lens agent so users can extend agent behavior with report templates and custom analysis workflows — no code changes required.

**Architecture:** A `use_skill` function_tool scans `persona_lens/skills/` (built-ins) and `~/.persona-lens/skills/` (user custom) at import time, builds a registry, and patches its own docstring with the live skill list. When Claude calls `use_skill("kol-report")`, the SKILL.md body is returned as a tool result, injecting the skill's instructions into the conversation context for Claude to follow.

**Tech Stack:** OpenAI Agents SDK (`agents`), PyYAML (already installed), Python 3.13, pytest

---

### Task 1: Skill loader + registry (`persona_lens/agent/skills.py`)

**Files:**
- Create: `persona_lens/agent/skills.py`
- Create: `tests/test_skills.py`

**Step 1: Write the failing tests**

```python
# tests/test_skills.py
import textwrap
from pathlib import Path
import pytest
from persona_lens.agent.skills import load_skills, _parse_skill_md


def test_parse_skill_md_returns_name_description_body(tmp_path):
    md = tmp_path / "SKILL.md"
    md.write_text(textwrap.dedent("""\
        ---
        name: test-skill
        description: A test skill for unit testing.
        ---
        # Test Skill
        Do the thing.
    """))
    name, meta, body = _parse_skill_md(md)
    assert name == "test-skill"
    assert meta["description"] == "A test skill for unit testing."
    assert "Do the thing." in body


def test_parse_skill_md_falls_back_to_dirname(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    md = skill_dir / "SKILL.md"
    md.write_text("No frontmatter here.")
    name, meta, body = _parse_skill_md(md)
    assert name == "my-skill"
    assert meta == {}


def test_load_skills_discovers_skills_in_directory(tmp_path):
    skill_dir = tmp_path / "greet"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: greet
        description: Greet the user.
        ---
        Say hello.
    """))
    skills = load_skills(builtin_dir=tmp_path, user_dir=None)
    assert "greet" in skills
    assert skills["greet"]["description"] == "Greet the user."
    assert "Say hello." in skills["greet"]["body"]


def test_load_skills_user_overrides_builtin(tmp_path):
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    for base in (builtin, user):
        d = base / "greet"
        d.mkdir(parents=True)
        source = "builtin" if base == builtin else "user"
        (d / "SKILL.md").write_text(textwrap.dedent(f"""\
            ---
            name: greet
            description: {source} version
            ---
            {source} body
        """))
    skills = load_skills(builtin_dir=builtin, user_dir=user)
    assert skills["greet"]["description"] == "user version"


def test_load_skills_skips_entries_without_description(tmp_path):
    d = tmp_path / "nodesc"
    d.mkdir()
    (d / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: nodesc
        ---
        Some body.
    """))
    skills = load_skills(builtin_dir=tmp_path, user_dir=None)
    assert "nodesc" not in skills
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_skills.py -v
```
Expected: `ModuleNotFoundError: No module named 'persona_lens.agent.skills'`

**Step 3: Implement `persona_lens/agent/skills.py`**

```python
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
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not match:
        return path.parent.name, {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    name = meta.get("name") or path.parent.name
    return name, meta, body


# ── Registry ──────────────────────────────────────────────────────────────────

def load_skills(
    builtin_dir: Path | None = None,
    user_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan directories for SKILL.md files and return registry dict."""
    builtin_dir = builtin_dir if builtin_dir is not None else _BUILTIN_DIR
    user_dir = user_dir if user_dir is not None else _USER_DIR

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


_SKILLS: dict[str, dict[str, Any]] = load_skills()


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


# Patch the docstring with the live skill list at import time.
use_skill.__doc__ = (use_skill.__doc__ or "").format(skill_list=_skill_list())
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_skills.py -v
```
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add persona_lens/agent/skills.py tests/test_skills.py
git commit -m "feat: add skill loader and use_skill tool"
```

---

### Task 2: Built-in skills

**Files:**
- Create: `persona_lens/skills/kol-report/SKILL.md`
- Create: `persona_lens/skills/competitor-analysis/SKILL.md`

**Step 1: Create `persona_lens/skills/kol-report/SKILL.md`**

```markdown
---
name: kol-report
description: Generate a structured KOL analysis report. Use when the user asks for a report, summary, or formatted output after analyzing an account.
---

# KOL Report Skill

After analysis data is available, output a structured report using this exact format:

---

## KOL Report: @{username}

### Account Overview
- **Display Name:** {display_name}
- **Bio:** {bio}
- **Followers:** {followers} | **Following:** {following} | **Tweets:** {tweets_count}

### Content Style
{writing_style}

### Products & Tools Mentioned
| Product | Category |
|---------|----------|
{products table rows}

### Posting Patterns
- **Peak Day:** {peak_day}
- **Peak Hour (UTC):** {peak_hour_utc}

### Top Performing Posts
{top_posts — text, likes, retweets for each}

### Engagement Insights
{engagement_insights}

---
*Report generated by persona-lens*
```

**Step 2: Create `persona_lens/skills/competitor-analysis/SKILL.md`**

```markdown
---
name: competitor-analysis
description: Compare two or more X/Twitter accounts side-by-side. Use when the user wants to compare, contrast, or evaluate multiple accounts together.
---

# Competitor Analysis Skill

When multiple accounts have been analyzed, produce a side-by-side comparison:

---

## Competitor Analysis

### Accounts Compared
List each username with follower count and bio.

### Content Style Comparison
For each account: 1-2 sentences on tone, vocabulary, format.

### Products & Focus Areas
Table: Account | Products | Primary Category

### Engagement Comparison
Table: Account | Avg Likes | Avg Retweets | Top Post Theme

### Posting Patterns
Table: Account | Peak Day | Peak Hour UTC

### Summary
2-3 sentences on key differentiators and positioning.

---
*Report generated by persona-lens*
```

**Step 3: Verify skills are discovered**

```bash
uv run python -c "
from persona_lens.agent.skills import _SKILLS
for name, s in _SKILLS.items():
    print(f'{name}: {s[\"description\"][:60]}')
"
```
Expected output:
```
competitor-analysis: Compare two or more X/Twitter accounts side-by...
kol-report: Generate a structured KOL analysis report. Use when the...
```

**Step 4: Commit**

```bash
git add persona_lens/skills/
git commit -m "feat: add built-in kol-report and competitor-analysis skills"
```

---

### Task 3: Wire `use_skill` into `main_agent`

**Files:**
- Modify: `persona_lens/agent/loop.py`

**Step 1: Write a test that verifies `use_skill` is in `main_agent.tools`**

Add to `tests/test_skills.py`:

```python
def test_use_skill_registered_on_main_agent():
    from persona_lens.agent.loop import main_agent
    from persona_lens.agent.skills import use_skill
    tool_names = [t.name for t in main_agent.tools]
    assert "use_skill" in tool_names
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_skills.py::test_use_skill_registered_on_main_agent -v
```
Expected: FAIL — `AssertionError: assert 'use_skill' not in [...]`

**Step 3: Add `use_skill` to `main_agent` in `loop.py`**

Change line 5–6 imports:
```python
# Before
from agents import Agent, ModelSettings, Runner, WebSearchTool
...
from persona_lens.platforms.x.agent import x_kol_agent
```
```python
# After
from agents import Agent, ModelSettings, Runner, WebSearchTool
...
from persona_lens.agent.skills import use_skill
from persona_lens.platforms.x.agent import x_kol_agent
```

Change `main_agent` tools list (line 28):
```python
# Before
    tools=[WebSearchTool()],
```
```python
# After
    tools=[WebSearchTool(), use_skill],
```

Also update `MAIN_SYSTEM_PROMPT` to mention skills:
```python
MAIN_SYSTEM_PROMPT = """You are a helpful assistant.
- For general questions, use web_search to find up-to-date information.
- When the user asks to analyze an X/Twitter account or user, hand off to the KOL Analysis Agent.
- When the user asks for a report, summary, or formatted output, use use_skill to load the appropriate skill instructions.
- Always reply in English."""
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_skills.py -v
```
Expected: all PASSED

**Step 5: Smoke-test import**

```bash
uv run python -c "from persona_lens.agent.loop import run_interactive_loop; print('ok')"
```
Expected: `ok`

**Step 6: Commit**

```bash
git add persona_lens/agent/loop.py
git commit -m "feat: wire use_skill into main_agent"
```

---

### Task 4: Update system prompt on x_kol_agent

**Files:**
- Modify: `persona_lens/platforms/x/agent.py`

The KOL agent hands back to `main_agent` after analysis. Skills live on `main_agent`, so no tool wiring needed here. But the KOL agent should mention that the user can request a report after analysis.

**Step 1: Update `KOL_SYSTEM_PROMPT`**

```python
# Before (last line of KOL_SYSTEM_PROMPT):
- Always reply in English."""

# After:
- After completing analysis, inform the user they can ask for a structured report.
- Always reply in English."""
```

**Step 2: Smoke test**

```bash
uv run python -c "from persona_lens.platforms.x.agent import x_kol_agent; print('ok')"
```
Expected: `ok`

**Step 3: Commit**

```bash
git add persona_lens/platforms/x/agent.py
git commit -m "feat: tell KOL agent to mention report option after analysis"
```

---

### Task 5: Final test run + docs

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```
Expected: all existing tests pass, new skill tests pass.

**Step 2: Commit design doc**

```bash
git add docs/plans/
git commit -m "docs: add agent skills design and implementation plan"
```
