"""Planning and applying links in a target directory (plan_links, apply_plan)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mloadout.bootstrap import BootstrapError, apply_plan, plan_links


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    """
    Provide a cache folder holding three skill folders: a, b and c

    **Args**:
        **tmp_path** (*Path*): the test's temp folder

    **Returns**:
        The cache root

    **Examples**:
        The skills live at `<cache>/src/<sha>/skills/<name>`, the same shape
        fetch_source produces.
    """
    root = tmp_path / "cache"
    for name in ("a", "b", "c"):
        (root / "src" / "sha" / "skills" / name).mkdir(parents=True)
    return root


def skill(
    cache: Path,
    name: str,
) -> Path:
    """Return the cache folder of one of the fixture skills."""
    return cache / "src" / "sha" / "skills" / name


def sync(
    target: Path,
    effective: dict[str, Path],
    cache: Path,
):
    """
    Plan and apply links in one step, returning the plan

    **Args**:
        **target** (*Path*): the target directory
        **effective** (*dict[str, Path]*): skill name to folder
        **cache** (*Path*): the cache root

    **Returns**:
        The LinkPlan that was applied

    **Examples**:
        >>> plan = sync(target=target, effective={"a": skill(cache, "a")}, cache=cache)
    """
    plan = plan_links(target=target, effective=effective, cache_dir=cache)
    apply_plan(plan=plan)
    return plan


def test_creates_missing_target_and_links(
    tmp_path: Path,
    cache: Path,
) -> None:
    """A first run creates the target directory and one link per skill."""
    target = tmp_path / "home" / ".agents" / "skills"

    plan = sync(
        target=target,
        effective={"a": skill(cache, "a"), "b": skill(cache, "b")},
        cache=cache,
    )

    assert sorted(plan.create) == ["a", "b"]
    assert (target / "a").is_symlink()
    assert (target / "a").resolve() == skill(cache, "a").resolve()


def test_second_run_changes_nothing(
    tmp_path: Path,
    cache: Path,
) -> None:
    """Running twice with the same set is a no-op."""
    target = tmp_path / "skills"
    effective = {"a": skill(cache, "a"), "b": skill(cache, "b")}
    sync(target=target, effective=effective, cache=cache)

    plan = sync(target=target, effective=effective, cache=cache)

    assert (plan.create, plan.update, plan.remove) == ({}, {}, [])
    assert sorted(plan.unchanged) == ["a", "b"]


def test_moved_skill_is_relinked(
    tmp_path: Path,
    cache: Path,
) -> None:
    """When a skill's folder changes (a new pin, or a replaces winner) the link is updated."""
    target = tmp_path / "skills"
    sync(target=target, effective={"a": skill(cache, "a")}, cache=cache)

    plan = sync(target=target, effective={"a": skill(cache, "b")}, cache=cache)

    assert list(plan.update) == ["a"]
    assert (target / "a").resolve() == skill(cache, "b").resolve()


def test_dropped_skill_link_is_removed(
    tmp_path: Path,
    cache: Path,
) -> None:
    """A skill no longer in the set loses its link, but its cache folder stays."""
    target = tmp_path / "skills"
    sync(
        target=target,
        effective={"a": skill(cache, "a"), "b": skill(cache, "b")},
        cache=cache,
    )

    plan = sync(target=target, effective={"a": skill(cache, "a")}, cache=cache)

    assert plan.remove == ["b"]
    assert not os.path.lexists(target / "b")
    assert skill(cache, "b").is_dir()


def test_broken_owned_link_is_removed(
    tmp_path: Path,
    cache: Path,
) -> None:
    """A link into the cache whose folder was deleted is still recognised and cleaned up."""
    target = tmp_path / "skills"
    target.mkdir()
    os.symlink(cache / "gone" / "skill", target / "gone", target_is_directory=True)

    plan = sync(target=target, effective={}, cache=cache)

    assert plan.remove == ["gone"]
    assert not os.path.lexists(target / "gone")


def test_entries_not_owned_by_bootstrap_are_left_alone(
    tmp_path: Path,
    cache: Path,
) -> None:
    """Hand-made folders and links pointing elsewhere are never removed."""
    target = tmp_path / "skills"
    (target / "my-own-skill").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, target / "foreign-link", target_is_directory=True)

    plan = sync(target=target, effective={"a": skill(cache, "a")}, cache=cache)

    assert plan.remove == []
    assert (target / "my-own-skill").is_dir()
    assert (target / "foreign-link").is_symlink()


@pytest.mark.parametrize("kind", ["folder", "foreign-link"])
def test_unowned_entry_with_wanted_name_fails(
    tmp_path: Path,
    cache: Path,
    kind: str,
) -> None:
    """A wanted name already taken by something bootstrap didn't make is a conflict."""
    target = tmp_path / "skills"
    target.mkdir()
    if kind == "folder":
        (target / "a").mkdir()
    else:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, target / "a", target_is_directory=True)

    with pytest.raises(BootstrapError) as error:
        plan_links(target=target, effective={"a": skill(cache, "a")}, cache_dir=cache)

    assert "was not created by bootstrap" in error.value.problems[0]


def test_relative_link_into_cache_counts_as_owned(
    tmp_path: Path,
    cache: Path,
) -> None:
    """Ownership is decided on the resolved destination, so relative links work too."""
    target = tmp_path / "skills"
    target.mkdir()
    os.symlink(
        os.path.relpath(skill(cache, "a"), target),
        target / "a",
        target_is_directory=True,
    )

    plan = plan_links(target=target, effective={}, cache_dir=cache)

    assert plan.remove == ["a"]
