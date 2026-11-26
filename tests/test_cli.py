"""The `mloadout` command itself and how it is packaged as a uv tool."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from mloadout import __version__
from mloadout.bootstrap import default_base_sources, load_config
from mloadout.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """`mloadout --version` prints the installed version and exits cleanly."""
    with pytest.raises(SystemExit) as exit_info:
        main(argv=["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"mloadout {__version__}"


def test_subcommand_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    """Running `mloadout` with no command is a usage error, not a silent no-op."""
    with pytest.raises(SystemExit) as exit_info:
        main(argv=[])

    assert exit_info.value.code == 2
    assert "<command>" in capsys.readouterr().err


def test_bootstrap_help_lists_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    """`mloadout bootstrap --help` documents the interface the overlay relies on."""
    with pytest.raises(SystemExit):
        main(argv=["bootstrap", "--help"])

    out = capsys.readouterr().out
    for option in ("--base", "--overlay", "--target", "--cache-dir", "--dry-run"):
        assert option in out


def test_default_base_is_the_repo_copy_in_a_checkout() -> None:
    """Run from the repo (an editable install), the base is the working skills/sources.yaml."""
    assert default_base_sources() == REPO_ROOT / "skills" / "sources.yaml"
    assert load_config(paths=[default_base_sources()]).backbone


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to build the wheel")
def test_wheel_bundles_sources_and_entry_point(tmp_path: Path) -> None:
    """The built wheel carries sources.yaml and the `mloadout` console script."""
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(REPO_ROOT)],
        check=True,
        capture_output=True,
    )
    (wheel,) = tmp_path.glob("mloadout-*.whl")

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        bundled = archive.read("mloadout/data/sources.yaml")
        entry_points = next(
            archive.read(name).decode()
            for name in names
            if name.endswith("entry_points.txt")
        )

    assert bundled == (REPO_ROOT / "skills" / "sources.yaml").read_bytes()
    assert "mloadout = mloadout.cli:main" in entry_points
    assert "mloadout/bootstrap.py" in names
