"""Loading and validating sources.yaml files (load_config, parse_source)."""

from __future__ import annotations

import pytest
from conftest import source_entry

from mloadout.bootstrap import BootstrapError, load_config


def problems_of(error: pytest.ExceptionInfo[BootstrapError]) -> str:
    """Join an error's problems into one string for substring checks."""
    return "\n".join(error.value.problems)


def test_valid_config_loads_sources_and_replaces(write_sources) -> None:
    """A valid file yields every source with its fields, plus the replaces entries."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {
                "main": source_entry(roots=["skills/a", "skills/b"]),
                "extra": source_entry(keep=["one", "two"], hold=True),
            },
            "replaces": [{"skill": "one", "use": "extra"}],
        }
    )

    config = load_config(paths=[path])

    assert config.backbone == "main"
    assert config.sources["main"].roots == ["skills/a", "skills/b"]
    assert config.sources["main"].keep is None
    assert config.sources["extra"].keep == ["one", "two"]
    assert config.sources["extra"].hold is True
    assert [(r.skill, r.use) for r in config.replaces] == [("one", "extra")]


def test_lab_section_is_ignored(write_sources) -> None:
    """Lab entries never become sources, even when they are incomplete."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {"main": source_entry()},
            "lab": {"challenger": {"keep": ["x"]}},
        }
    )

    config = load_config(paths=[path])

    assert list(config.sources) == ["main"]


@pytest.mark.parametrize(
    "stable",
    ["TODO", "5863806", "A" * 40, "g" * 40, "a" * 41],
    ids=["todo", "short-sha", "uppercase", "not-hex", "too-long"],
)
def test_stable_must_be_full_lowercase_sha(
    write_sources,
    stable: str,
) -> None:
    """Anything but a full 40-character hex SHA is rejected, never a tag or short SHA."""
    path = write_sources(
        {"backbone": "main", "sources": {"main": source_entry(stable=stable)}}
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "stable must be a full 40-character commit SHA" in problems_of(error)


@pytest.mark.parametrize(
    "roots",
    [[], ["TODO"], ["/etc"], ["skills/../.."]],
    ids=["empty", "todo", "absolute", "parent-traversal"],
)
def test_roots_must_be_relative_and_resolved(
    write_sources,
    roots: list[str],
) -> None:
    """Roots must be filled in and stay inside the source repo."""
    path = write_sources(
        {"backbone": "main", "sources": {"main": source_entry(roots=roots)}}
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "roots must" in problems_of(error)


def test_unset_licence_is_rejected(write_sources) -> None:
    """A licence of TODO fails, even on a source that is on hold."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {
                "main": source_entry(),
                "held": source_entry(keep=["x"], licence="TODO", hold=True),
            },
        }
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "source 'held': licence is not set" in problems_of(error)


def test_non_backbone_source_needs_keep_list(write_sources) -> None:
    """Only the backbone may be all-on; every other source must list what it keeps."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {"main": source_entry(), "extra": source_entry()},
        }
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "source 'extra' needs a keep list" in problems_of(error)


def test_backbone_must_be_declared(write_sources) -> None:
    """A config without a backbone fails."""
    path = write_sources({"sources": {"main": source_entry(keep=["x"])}})

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "exactly one backbone must be declared" in problems_of(error)


def test_backbone_must_name_a_source(write_sources) -> None:
    """The backbone has to be one of the declared sources."""
    path = write_sources(
        {"backbone": "missing", "sources": {"main": source_entry(keep=["x"])}}
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "backbone 'missing' is not a declared source" in problems_of(error)


def test_invalid_backbone_reports_only_the_real_problem(write_sources) -> None:
    """A backbone with a bad field isn't also reported as undeclared."""
    path = write_sources(
        {"backbone": "main", "sources": {"main": source_entry(stable="TODO")}}
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert len(error.value.problems) == 1
    assert "stable must be" in error.value.problems[0]


def test_overlay_adds_sources(write_sources) -> None:
    """A second file (an employer overlay) adds its sources to the first file's."""
    base = write_sources({"backbone": "main", "sources": {"main": source_entry()}})
    overlay = write_sources(
        {"sources": {"internal": source_entry(keep=["x"])}},
        name="overlay.yaml",
    )

    config = load_config(paths=[base, overlay])

    assert set(config.sources) == {"main", "internal"}
    assert config.sources["internal"].declared_in == overlay


def test_overlay_cannot_redeclare_a_source(write_sources) -> None:
    """A source name declared in two files fails rather than one silently winning."""
    base = write_sources({"backbone": "main", "sources": {"main": source_entry()}})
    overlay = write_sources(
        {"sources": {"main": source_entry(keep=["x"])}},
        name="overlay.yaml",
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[base, overlay])

    assert "source 'main' is already declared" in problems_of(error)


def test_overlay_cannot_declare_a_second_backbone(write_sources) -> None:
    """Only one file may declare the backbone."""
    base = write_sources({"backbone": "main", "sources": {"main": source_entry()}})
    overlay = write_sources(
        {"backbone": "internal", "sources": {"internal": source_entry()}},
        name="overlay.yaml",
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[base, overlay])

    assert "exactly one backbone must be declared" in problems_of(error)


def test_malformed_replaces_entry_is_rejected(write_sources) -> None:
    """Each replaces entry needs both `skill` and `use`."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {"main": source_entry()},
            "replaces": [{"skill": "tdd"}],
        }
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert "each replaces entry needs 'skill' and 'use'" in problems_of(error)


def test_all_problems_are_reported_together(write_sources) -> None:
    """Problems across sources are collected, so one run shows everything to fix."""
    path = write_sources(
        {
            "backbone": "main",
            "sources": {
                "main": source_entry(stable="TODO"),
                "extra": source_entry(keep=["x"], roots=["TODO"], licence="TODO"),
            },
        }
    )

    with pytest.raises(BootstrapError) as error:
        load_config(paths=[path])

    assert len(error.value.problems) == 3


def test_repo_sources_file_is_valid() -> None:
    """The sources.yaml committed in this repo passes every config check."""
    from mloadout.bootstrap import default_base_sources

    config = load_config(paths=[default_base_sources()])

    assert config.backbone in config.sources
