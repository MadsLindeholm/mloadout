"""Fetching sources into the cache at their pinned commit (fetch_source)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import skill_md

from bootstrap import BootstrapError, Source, fetch_source


def make_source(
    url: str,
    stable: str,
) -> Source:
    """
    Build a Source pointing at a fake upstream

    **Args**:
        **url** (*str*): the upstream repo URL
        **stable** (*str*): the commit to pin

    **Returns**:
        A Source named "upstream" with root "skills"

    **Examples**:
        >>> make_source(url=repo.url, stable=sha)
    """
    return Source(
        name="upstream",
        repo=url,
        stable=stable,
        roots=["skills"],
        keep=None,
        hold=False,
        declared_in=Path("sources.yaml"),
    )


def head_of(checkout: Path) -> str:
    """Return the commit a checkout is at."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_fetches_the_pinned_commit_not_head(
    make_repo,
    tmp_path: Path,
) -> None:
    """The checkout is at `stable` even when upstream has moved on."""
    repo = make_repo("upstream")
    pinned = repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})
    repo.commit(files={"skills/b/SKILL.md": skill_md(name="b")})

    checkout = fetch_source(
        source=make_source(url=repo.url, stable=pinned),
        cache_dir=tmp_path / "cache",
    )

    assert checkout == tmp_path / "cache" / "upstream" / pinned
    assert head_of(checkout=checkout) == pinned
    assert (checkout / "skills" / "a" / "SKILL.md").is_file()
    assert not (checkout / "skills" / "b").exists()


def test_reuses_an_existing_checkout(
    make_repo,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A second fetch of the same commit doesn't touch the network."""
    repo = make_repo("upstream")
    sha = repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})
    source = make_source(url=repo.url, stable=sha)
    fetch_source(source=source, cache_dir=tmp_path / "cache")
    capsys.readouterr()

    fetch_source(source=source, cache_dir=tmp_path / "cache")

    assert "fetching" not in capsys.readouterr().out


def test_replaces_a_broken_checkout(
    make_repo,
    tmp_path: Path,
) -> None:
    """A cache folder that isn't a valid checkout at `stable` is fetched again."""
    repo = make_repo("upstream")
    sha = repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})
    broken = tmp_path / "cache" / "upstream" / sha
    broken.mkdir(parents=True)
    (broken / "leftover.txt").write_text("not a checkout", encoding="utf-8")

    checkout = fetch_source(
        source=make_source(url=repo.url, stable=sha),
        cache_dir=tmp_path / "cache",
    )

    assert head_of(checkout=checkout) == sha
    assert not (checkout / "leftover.txt").exists()


def test_cleans_up_a_partial_fetch(
    make_repo,
    tmp_path: Path,
) -> None:
    """Staging left by an interrupted run is removed and the fetch succeeds."""
    repo = make_repo("upstream")
    sha = repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})
    staging = tmp_path / "cache" / "upstream" / f".{sha}.partial"
    staging.mkdir(parents=True)

    fetch_source(
        source=make_source(url=repo.url, stable=sha),
        cache_dir=tmp_path / "cache",
    )

    assert not staging.exists()


def test_unknown_commit_fails(
    make_repo,
    tmp_path: Path,
) -> None:
    """Pinning a commit that doesn't exist upstream fails with git's message."""
    repo = make_repo("upstream")
    repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})

    with pytest.raises(BootstrapError) as error:
        fetch_source(
            source=make_source(url=repo.url, stable="0" * 40),
            cache_dir=tmp_path / "cache",
        )

    assert "git fetch" in error.value.problems[0]
    assert not (tmp_path / "cache" / "upstream" / ("0" * 40)).exists()
