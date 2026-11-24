"""End-to-end runs of the bootstrap command (main) against fake upstream repos."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import skill_md, source_entry

from mloadout.cli import main


@pytest.fixture
def upstreams(make_repo) -> dict[str, tuple[str, str]]:
    """
    Create two fake upstreams: a backbone with two skills, and an extra with two

    **Args**:
        **make_repo** (*Callable*): the repo factory fixture

    **Returns**:
        Source name to (repo URL, pinned SHA)

    **Examples**:
        The backbone has `tdd` and `teach`; the extra has `unslop` and `tdd`,
        so keeping the extra's `tdd` creates a collision.
    """
    backbone = make_repo("backbone")
    backbone_sha = backbone.commit(
        files={
            "skills/tdd/SKILL.md": skill_md(name="tdd"),
            "skills/teach/SKILL.md": skill_md(name="teach"),
        }
    )
    extra = make_repo("extra")
    extra_sha = extra.commit(
        files={
            "skills/unslop/SKILL.md": skill_md(name="unslop"),
            "skills/tdd/SKILL.md": skill_md(name="tdd"),
        }
    )
    return {"backbone": (backbone.url, backbone_sha), "extra": (extra.url, extra_sha)}


def config(
    upstreams: dict[str, tuple[str, str]],
    extra_keep: list[str],
    **extra_fields,
) -> dict:
    """
    Build sources.yaml content for the two fake upstreams

    **Args**:
        **upstreams** (*dict[str, tuple[str, str]]*): from the upstreams fixture
        **extra_keep** (*list[str]*): the keep list for the extra source
        **extra_fields**: additional fields for the extra source, such as hold

    **Returns**:
        The sources.yaml content as a dict

    **Examples**:
        >>> config(upstreams=upstreams, extra_keep=["unslop"], hold=True)
    """
    backbone_url, backbone_sha = upstreams["backbone"]
    extra_url, extra_sha = upstreams["extra"]
    return {
        "backbone": "backbone",
        "sources": {
            "backbone": source_entry(repo=backbone_url, stable=backbone_sha),
            "extra": source_entry(repo=extra_url, stable=extra_sha, keep=extra_keep)
            | extra_fields,
        },
    }


def run(
    tmp_path: Path,
    sources: Path,
    *extra_args: str,
    targets: tuple[str, ...] = ("skills",),
) -> int:
    """
    Run `mloadout bootstrap` with a cache and targets inside the test's temp folder

    **Args**:
        **tmp_path** (*Path*): the test's temp folder
        **sources** (*Path*): the base sources.yaml to use
        **extra_args** (*str*): further command-line arguments, such as --dry-run
        **targets** (*tuple[str, ...]*): target folder names under tmp_path

    **Returns**:
        The exit code from main()

    **Examples**:
        >>> run(tmp_path, sources, "--dry-run")
    """
    argv = [
        "bootstrap",
        "--base",
        str(sources),
        "--cache-dir",
        str(tmp_path / "cache"),
        *extra_args,
    ]
    for target in targets:
        argv += ["--target", str(tmp_path / target)]
    return main(argv=argv)


def linked(target: Path) -> set[str]:
    """Return the names of the entries in a target folder."""
    return {entry.name for entry in target.iterdir()} if target.exists() else set()


def test_links_backbone_and_kept_skills(
    tmp_path: Path,
    upstreams,
    write_sources,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean run links every backbone skill plus the kept ones, and says so."""
    sources = write_sources(config(upstreams=upstreams, extra_keep=["unslop"]))

    assert run(tmp_path, sources) == 0

    assert linked(tmp_path / "skills") == {"tdd", "teach", "unslop"}
    assert "3 skills from 2 sources (backbone 2, extra 1)" in capsys.readouterr().out


def test_dry_run_changes_no_links(
    tmp_path: Path,
    upstreams,
    write_sources,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--dry-run prints the plan without creating anything in the target."""
    sources = write_sources(config(upstreams=upstreams, extra_keep=["unslop"]))

    assert run(tmp_path, sources, "--dry-run") == 0

    assert not (tmp_path / "skills").exists()
    assert "would change 3" in capsys.readouterr().out


def test_held_source_is_not_linked(
    tmp_path: Path,
    upstreams,
    write_sources,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A source with hold: true is skipped entirely, and the run says it's holding it."""
    sources = write_sources(
        config(upstreams=upstreams, extra_keep=["unslop"], hold=True)
    )

    assert run(tmp_path, sources) == 0

    assert linked(tmp_path / "skills") == {"tdd", "teach"}
    assert not (tmp_path / "cache" / "extra").exists()
    assert "holding extra" in capsys.readouterr().out


def test_failing_check_changes_no_links(
    tmp_path: Path,
    upstreams,
    write_sources,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When any check fails, existing links stay exactly as they were."""
    good = write_sources(config(upstreams=upstreams, extra_keep=["unslop"]))
    assert run(tmp_path, good) == 0
    before = {
        name: os.readlink(tmp_path / "skills" / name)
        for name in linked(tmp_path / "skills")
    }
    bad = write_sources(
        config(upstreams=upstreams, extra_keep=["unslop", "tdd"]),
        name="bad.yaml",
    )

    assert run(tmp_path, bad) == 1

    after = {
        name: os.readlink(tmp_path / "skills" / name)
        for name in linked(tmp_path / "skills")
    }
    assert after == before
    err = capsys.readouterr().err
    assert "bootstrap failed; no links were changed" in err
    assert "skill 'tdd' is offered by ['backbone', 'extra']" in err


def test_replaces_resolves_a_collision(
    tmp_path: Path,
    upstreams,
    write_sources,
) -> None:
    """With a replaces entry the run succeeds and links the chosen source's copy."""
    data = config(upstreams=upstreams, extra_keep=["unslop", "tdd"])
    data["replaces"] = [{"skill": "tdd", "use": "extra"}]
    sources = write_sources(data)

    assert run(tmp_path, sources) == 0

    assert "extra" in Path(os.readlink(tmp_path / "skills" / "tdd")).parts


def test_bumping_stable_relinks_to_the_new_commit(
    tmp_path: Path,
    make_repo,
    write_sources,
) -> None:
    """Moving stable to a newer commit points the links at the new checkout."""
    repo = make_repo("only")
    old = repo.commit(files={"skills/tdd/SKILL.md": skill_md(name="tdd")})
    new = repo.commit(
        files={"skills/tdd/SKILL.md": skill_md(name="tdd", description="Newer.")}
    )
    data = {
        "backbone": "only",
        "sources": {"only": source_entry(repo=repo.url, stable=old)},
    }
    assert run(tmp_path, write_sources(data)) == 0

    data["sources"]["only"]["stable"] = new
    assert run(tmp_path, write_sources(data)) == 0

    assert new in Path(os.readlink(tmp_path / "skills" / "tdd")).parts


def test_links_into_every_target(
    tmp_path: Path,
    upstreams,
    write_sources,
) -> None:
    """Each --target gets its own full set of links."""
    sources = write_sources(config(upstreams=upstreams, extra_keep=["unslop"]))

    assert run(tmp_path, sources, targets=("agents", "fallback")) == 0

    assert (
        linked(tmp_path / "agents")
        == linked(tmp_path / "fallback")
        == {"tdd", "teach", "unslop"}
    )


def test_conflict_in_one_target_blocks_all_targets(
    tmp_path: Path,
    upstreams,
    write_sources,
) -> None:
    """Every target is planned before any is changed, so one conflict stops them all."""
    sources = write_sources(config(upstreams=upstreams, extra_keep=["unslop"]))
    (tmp_path / "fallback" / "tdd").mkdir(parents=True)

    assert run(tmp_path, sources, targets=("agents", "fallback")) == 1

    assert not (tmp_path / "agents").exists()


def test_invalid_config_fetches_nothing(
    tmp_path: Path,
    upstreams,
    write_sources,
) -> None:
    """Config errors stop the run before any network access."""
    data = config(upstreams=upstreams, extra_keep=["unslop"])
    data["sources"]["extra"]["stable"] = "TODO"

    assert run(tmp_path, write_sources(data)) == 1

    assert not (tmp_path / "cache").exists()


def test_overlay_adds_its_sources_to_the_base(
    tmp_path: Path,
    upstreams,
    write_sources,
) -> None:
    """An overlay file contributes its own sources on top of the base file."""
    data = config(upstreams=upstreams, extra_keep=["unslop"])
    base = write_sources(
        {"backbone": "backbone", "sources": {"backbone": data["sources"]["backbone"]}}
    )
    overlay = write_sources(
        {"sources": {"extra": data["sources"]["extra"]}}, name="overlay.yaml"
    )

    assert run(tmp_path, base, "--overlay", str(overlay)) == 0

    assert linked(tmp_path / "skills") == {"tdd", "teach", "unslop"}
