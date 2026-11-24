"""Shared fixtures: isolated git, fake upstream repos and sources.yaml builders."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml


def skill_md(
    name: str,
    description: str = "A test skill.",
) -> str:
    """
    Build the text of a minimal valid SKILL.md

    **Args**:
        **name** (*str*): the skill name written into the frontmatter
        **description** (*str*): the description written into the frontmatter

    **Returns**:
        The SKILL.md text, frontmatter followed by a short body

    **Examples**:
        >>> skill_md(name="tdd")
        Gives `---`, `name: tdd`, `description: A test skill.`, `---` and a body
        line. Pass a different name than the folder to test mismatches.
    """
    return f"---\nname: {name}\ndescription: {description}\n---\n\nBody of {name}.\n"


class UpstreamRepo:
    """A local git repo standing in for a third-party skill source."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.url = path.as_uri()
        path.mkdir(parents=True)
        self._git("init", "--quiet", "--initial-branch=main")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, files: dict[str, str | None]) -> str:
        """
        Write, change or delete files and commit them

        **Args**:
            **files** (*dict[str, str | None]*): repo-relative path to new content, or None to delete

        **Returns**:
            The full SHA of the new commit

        **Examples**:
            >>> sha = repo.commit(
            ...     files={"skills/tdd/SKILL.md": skill_md(name="tdd")}
            ... )
            Each call makes one commit on main, so earlier SHAs stay fetchable
            and can be used as pinned `stable` values.
        """
        for relative, content in files.items():
            target = self.path / relative
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self._git("add", "--all")
        self._git("commit", "--quiet", "--allow-empty", "-m", "update")
        return self._git("rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def isolated_git(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Keep every git call away from the user's own git configuration

    **Args**:
        **tmp_path_factory** (*pytest.TempPathFactory*): source of a scratch folder for an empty config
        **monkeypatch** (*pytest.MonkeyPatch*): used to set environment variables for the test

    **Returns**:
        Nothing

    **Examples**:
        Applied to every test automatically. Global and system config are
        ignored, so settings like commit signing or URL rewrites can't change
        results, and commits get a fixed author.
    """
    config_dir = tmp_path_factory.mktemp("gitconfig")
    empty_config = config_dir / "config"
    empty_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for variable in ("GIT_AUTHOR", "GIT_COMMITTER"):
        monkeypatch.setenv(f"{variable}_NAME", "mloadout tests")
        monkeypatch.setenv(f"{variable}_EMAIL", "tests@example.invalid")


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[[str], UpstreamRepo]:
    """
    Provide a factory for fake upstream repos inside the test's temp folder

    **Args**:
        **tmp_path** (*Path*): the test's temp folder

    **Returns**:
        A function that takes a repo name and returns a new, empty UpstreamRepo

    **Examples**:
        >>> repo = make_repo("superpowers")
        >>> sha = repo.commit(files={"skills/a/SKILL.md": skill_md(name="a")})
    """

    def factory(name: str) -> UpstreamRepo:
        return UpstreamRepo(path=tmp_path / "upstream" / name)

    return factory


@pytest.fixture
def write_sources(tmp_path: Path) -> Callable[..., Path]:
    """
    Provide a factory that writes a sources.yaml file and returns its path

    **Args**:
        **tmp_path** (*Path*): the test's temp folder

    **Returns**:
        A function taking the file's content as a dict and an optional file name

    **Examples**:
        >>> path = write_sources(
        ...     {"backbone": "a", "sources": {"a": source_entry(...)}},
        ...     name="overlay.yaml",
        ... )
    """

    def factory(
        data: dict,
        name: str = "sources.yaml",
    ) -> Path:
        path = tmp_path / "config" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    return factory


def source_entry(
    repo: str = "https://example.invalid/repo",
    stable: str = "a" * 40,
    roots: list[str] | None = None,
    keep: list[str] | None = None,
    licence: str = "MIT",
    hold: bool | None = None,
) -> dict:
    """
    Build one `sources:` entry with valid defaults

    **Args**:
        **repo** (*str*): the repo URL
        **stable** (*str*): the pinned commit SHA
        **roots** (*list[str] | None*): skill roots, defaulting to ["skills"]
        **keep** (*list[str] | None*): the keep list, left out when None
        **licence** (*str*): the licence identifier
        **hold** (*bool | None*): the hold flag, left out when None

    **Returns**:
        A dict ready to put under a source name in sources.yaml

    **Examples**:
        >>> source_entry(repo=repo.url, stable=sha, keep=["tdd"])
        Override one field at a time to test a single validation rule.
    """
    entry: dict = {
        "repo": repo,
        "stable": stable,
        "roots": roots if roots is not None else ["skills"],
        "licence": licence,
    }
    if keep is not None:
        entry["keep"] = keep
    if hold is not None:
        entry["hold"] = hold
    return entry
