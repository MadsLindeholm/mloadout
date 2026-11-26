"""Choosing skills from a checkout and merging sources (select_skills, resolve_collisions)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import skill_md

from mloadout.bootstrap import (
    BootstrapError,
    Replacement,
    Source,
    resolve_collisions,
    select_skills,
)


def write_checkout(
    root: Path,
    files: dict[str, str],
) -> Path:
    """
    Lay out files as if they were a fetched checkout

    **Args**:
        **root** (*Path*): the folder to act as the checkout
        **files** (*dict[str, str]*): checkout-relative path to file content

    **Returns**:
        The checkout folder

    **Examples**:
        >>> write_checkout(
        ...     root=tmp_path / "checkout",
        ...     files={"skills/tdd/SKILL.md": skill_md(name="tdd")},
        ... )
        Selection doesn't need git, so these tests use plain folders.
    """
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def make_source(
    roots: list[str],
    keep: list[str] | None = None,
) -> Source:
    """
    Build a Source for selection tests

    **Args**:
        **roots** (*list[str]*): the roots to read skills from
        **keep** (*list[str] | None*): the keep list, or None for an all-on source

    **Returns**:
        A Source named "src" pinned to a dummy SHA

    **Examples**:
        >>> make_source(roots=["skills"], keep=["tdd"])
    """
    return Source(
        name="src",
        repo="https://example.invalid/repo",
        stable="a" * 40,
        roots=roots,
        keep=keep,
        hold=False,
        declared_in=Path("sources.yaml"),
    )


# --------------------------------------------------------------------------- select_skills


def test_backbone_takes_every_skill_in_its_roots(tmp_path: Path) -> None:
    """All-on means every folder with a SKILL.md, in every listed root, and nothing else."""
    checkout = write_checkout(
        root=tmp_path,
        files={
            "skills/engineering/tdd/SKILL.md": skill_md(name="tdd"),
            "skills/engineering/README.md": "not a skill",
            "skills/engineering/notes/plan.md": "folder without SKILL.md",
            "skills/productivity/teach/SKILL.md": skill_md(name="teach"),
            "skills/misc/ignored/SKILL.md": skill_md(name="ignored"),
        },
    )

    selected = select_skills(
        source=make_source(roots=["skills/engineering", "skills/productivity"]),
        checkout=checkout,
        is_backbone=True,
    )

    assert selected == {
        "tdd": checkout / "skills/engineering/tdd",
        "teach": checkout / "skills/productivity/teach",
    }


def test_keep_list_limits_selection(tmp_path: Path) -> None:
    """A non-backbone source contributes only the skills it keeps."""
    checkout = write_checkout(
        root=tmp_path,
        files={
            "skills/unslop/SKILL.md": skill_md(name="unslop"),
            "skills/swarm/SKILL.md": skill_md(name="swarm"),
        },
    )

    selected = select_skills(
        source=make_source(roots=["skills"], keep=["unslop"]),
        checkout=checkout,
        is_backbone=False,
    )

    assert selected == {"unslop": checkout / "skills/unslop"}


def test_keep_name_missing_upstream_fails(tmp_path: Path) -> None:
    """An upstream rename or removal fails loudly instead of silently dropping the skill."""
    checkout = write_checkout(
        root=tmp_path,
        files={"skills/unslop/SKILL.md": skill_md(name="unslop")},
    )

    with pytest.raises(BootstrapError) as error:
        select_skills(
            source=make_source(roots=["skills"], keep=["unslop", "renamed"]),
            checkout=checkout,
            is_backbone=False,
        )

    assert error.value.problems == [
        "src: keep name 'renamed' no longer exists upstream (roots ['skills'] at aaaaaaaaaaaa)"
    ]


def test_missing_root_fails(tmp_path: Path) -> None:
    """A root that doesn't exist at the pinned commit is reported."""
    checkout = write_checkout(
        root=tmp_path,
        files={"skills/a/SKILL.md": skill_md(name="a")},
    )

    with pytest.raises(BootstrapError) as error:
        select_skills(
            source=make_source(roots=["skills", "plugins/x/skills"]),
            checkout=checkout,
            is_backbone=True,
        )

    assert "root 'plugins/x/skills' does not exist" in error.value.problems[0]


def test_skill_in_two_roots_fails(tmp_path: Path) -> None:
    """A keep name found in more than one root is ambiguous."""
    checkout = write_checkout(
        root=tmp_path,
        files={
            "one/tdd/SKILL.md": skill_md(name="tdd"),
            "two/tdd/SKILL.md": skill_md(name="tdd"),
        },
    )

    with pytest.raises(BootstrapError) as error:
        select_skills(
            source=make_source(roots=["one", "two"], keep=["tdd"]),
            checkout=checkout,
            is_backbone=False,
        )

    assert "skill 'tdd' is in more than one root" in error.value.problems[0]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("# No frontmatter\n", "has no frontmatter"),
        ("---\nname: [unclosed\n---\n", "frontmatter does not parse"),
        ("---\n- a list\n---\n", "frontmatter is not a mapping"),
        (skill_md(name="other-name"), "names itself 'other-name'"),
        ("---\nname: tdd\n---\n", "has no description"),
    ],
    ids=[
        "no-frontmatter",
        "bad-yaml",
        "not-mapping",
        "name-mismatch",
        "no-description",
    ],
)
def test_invalid_frontmatter_fails(
    tmp_path: Path,
    content: str,
    expected: str,
) -> None:
    """Every selected SKILL.md needs frontmatter naming its folder, plus a description."""
    checkout = write_checkout(root=tmp_path, files={"skills/tdd/SKILL.md": content})

    with pytest.raises(BootstrapError) as error:
        select_skills(
            source=make_source(roots=["skills"], keep=["tdd"]),
            checkout=checkout,
            is_backbone=False,
        )

    assert expected in error.value.problems[0]


def test_frontmatter_with_windows_line_endings_is_accepted(tmp_path: Path) -> None:
    """A SKILL.md checked out with CRLF line endings still parses."""
    checkout = write_checkout(
        root=tmp_path,
        files={"skills/tdd/SKILL.md": skill_md(name="tdd").replace("\n", "\r\n")},
    )

    selected = select_skills(
        source=make_source(roots=["skills"], keep=["tdd"]),
        checkout=checkout,
        is_backbone=False,
    )

    assert list(selected) == ["tdd"]


def test_extra_frontmatter_fields_are_allowed(tmp_path: Path) -> None:
    """Standard optional fields like disable-model-invocation don't fail the check."""
    content = "---\nname: unslop\ndescription: Cut AI tells.\ndisable-model-invocation: true\n---\n"
    checkout = write_checkout(root=tmp_path, files={"skills/unslop/SKILL.md": content})

    selected = select_skills(
        source=make_source(roots=["skills"], keep=["unslop"]),
        checkout=checkout,
        is_backbone=False,
    )

    assert list(selected) == ["unslop"]


# --------------------------------------------------------------------------- resolve_collisions


def replacement(
    skill: str,
    use: str,
) -> Replacement:
    """Build a Replacement declared in a dummy file."""
    return Replacement(skill=skill, use=use, declared_in=Path("sources.yaml"))


def test_distinct_names_merge() -> None:
    """Skills from different sources with different names all make it into the set."""
    effective = resolve_collisions(
        selections={
            "a": {"tdd": Path("/a/tdd")},
            "b": {"unslop": Path("/b/unslop")},
        },
        replaces=[],
    )

    assert effective == {"tdd": Path("/a/tdd"), "unslop": Path("/b/unslop")}


def test_undeclared_collision_fails() -> None:
    """Two sources offering the same name fail unless a replaces entry picks one."""
    with pytest.raises(BootstrapError) as error:
        resolve_collisions(
            selections={"a": {"tdd": Path("/a/tdd")}, "b": {"tdd": Path("/b/tdd")}},
            replaces=[],
        )

    assert "skill 'tdd' is offered by ['a', 'b']" in error.value.problems[0]


def test_replaces_picks_the_winner() -> None:
    """A replaces entry decides which source's copy is linked."""
    effective = resolve_collisions(
        selections={"a": {"tdd": Path("/a/tdd")}, "b": {"tdd": Path("/b/tdd")}},
        replaces=[replacement(skill="tdd", use="b")],
    )

    assert effective == {"tdd": Path("/b/tdd")}


def test_stale_replaces_entry_fails() -> None:
    """A replaces entry with no collision left is reported so it gets cleaned up."""
    with pytest.raises(BootstrapError) as error:
        resolve_collisions(
            selections={"a": {"tdd": Path("/a/tdd")}},
            replaces=[replacement(skill="tdd", use="a")],
        )

    assert "no collision to resolve" in error.value.problems[0]


def test_replaces_must_name_a_provider() -> None:
    """The winning source must be one that actually offers the skill."""
    with pytest.raises(BootstrapError) as error:
        resolve_collisions(
            selections={"a": {"tdd": Path("/a/tdd")}, "b": {"tdd": Path("/b/tdd")}},
            replaces=[replacement(skill="tdd", use="c")],
        )

    assert "'c' is not one of ['a', 'b']" in error.value.problems[0]


def test_replaces_declared_twice_fails() -> None:
    """Declaring the same collision twice is ambiguous and fails."""
    with pytest.raises(BootstrapError) as error:
        resolve_collisions(
            selections={"a": {"tdd": Path("/a/tdd")}, "b": {"tdd": Path("/b/tdd")}},
            replaces=[
                replacement(skill="tdd", use="a"),
                replacement(skill="tdd", use="b"),
            ],
        )

    assert "declared more than once" in error.value.problems[0]
