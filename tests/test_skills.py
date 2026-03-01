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
