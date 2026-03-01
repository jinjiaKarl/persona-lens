# Agent Skills System Design

**Date:** 2026-03-01
**Status:** Approved

## Problem

The persona-lens agent has fixed behavior — its analysis workflows and output formats are hardcoded in system prompts. There is no way to extend or customize the agent without modifying source code.

## Goal

Add a SKILL.md-based skills system to the persona-lens agent so that:
1. Built-in skills (report templates, analysis workflows) ship with the package
2. Users can add their own skills locally without touching source code

## Non-Goals

- Migration away from OpenAI Agents SDK
- Skills that execute arbitrary code (skills inject prompt instructions only)
- Web UI for managing skills

---

## Design

### Skill Format

Skills are directories containing a `SKILL.md` file with YAML frontmatter:

```
persona_lens/skills/
  kol-report/
    SKILL.md
  competitor-analysis/
    SKILL.md

~/.persona-lens/skills/
  my-custom/
    SKILL.md
```

`SKILL.md` structure:

```markdown
---
name: kol-report
description: Generate a structured KOL analysis report. Use when the user asks for a report, summary, or formatted output of an analyzed account.
---

# KOL Report Skill

After analysis is complete, output the following structure:
...
```

Required frontmatter fields: `name`, `description`.
The `description` determines when Claude invokes the skill (LLM reasoning, no keyword matching).

### Skill Discovery

At import time, `persona_lens/agent/skills.py` scans two directories in order:

1. `persona_lens/skills/` — built-in skills (package-bundled)
2. `~/.persona-lens/skills/` — user custom skills

User skills with the same name override built-in skills. The registry is built once at startup.

### `use_skill` Tool

A single `@function_tool` registered on `main_agent`:

```python
@function_tool
def use_skill(ctx: RunContextWrapper, command: str) -> str:
    """Invoke a skill by name to follow specialized instructions.

    Available skills:
    {dynamically generated list: "- name: description"}

    Args:
        command: skill name to invoke
    """
    skill = _SKILLS.get(command)
    if not skill:
        return f"Skill '{command}' not found. Available: {', '.join(_SKILLS)}"
    return skill["body"]  # SKILL.md body injected into LLM context as tool output
```

The tool description is patched at module load time with the live skill list. Claude reads this list and uses language understanding to decide when to call `use_skill`.

### How Injection Works

When Claude calls `use_skill("kol-report")`, the SKILL.md body becomes a `function_call_output` in the conversation history — visible to Claude in the next turn. Claude then follows the injected instructions.

This mirrors the Claude Agent SDK mechanism:
- Claude Agent SDK: injects as hidden user message (`isMeta: true`)
- Our implementation: injects as tool result (`function_call_output`)

Both are available to the LLM; neither requires additional code execution.

### Integration Points

- `agent/skills.py` — skill loader, registry, `use_skill` tool definition
- `agent/loop.py` — add `use_skill` to `main_agent.tools`
- `persona_lens/skills/` — built-in skill files (new directory)

The FastAPI server (`api/server.py`) uses the same `main_agent`, so skills are available in both CLI and API modes with no additional changes.

---

## Built-in Skills (Initial Set)

| Skill | Description |
|-------|-------------|
| `kol-report` | Generate a structured KOL analysis report with sections for overview, content style, products, engagement, and posting patterns |
| `competitor-analysis` | Compare two or more analyzed accounts side-by-side |

---

## File Layout

```
persona_lens/
  agent/
    skills.py          ← NEW: loader + use_skill tool
    loop.py            ← MODIFIED: add use_skill to main_agent
  skills/
    kol-report/
      SKILL.md         ← NEW
    competitor-analysis/
      SKILL.md         ← NEW
tests/
  test_skills.py       ← NEW
```

---

## User Customization

Users create skills by adding directories to `~/.persona-lens/skills/`:

```bash
mkdir -p ~/.persona-lens/skills/my-report
cat > ~/.persona-lens/skills/my-report/SKILL.md << 'EOF'
---
name: my-report
description: Generate a custom investment memo for KOLs in the AI space.
---

# My Report Skill
...
EOF
```

Restart persona-lens to pick up new skills. No code changes required.
