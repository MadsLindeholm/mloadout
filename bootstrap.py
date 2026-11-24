#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6"]
# ///
"""
Link pinned third-party Agent Skills into the shared skills directory (ADR 0002)

Reads one or more sources.yaml files, fetches each source at its pinned `stable`
commit into a cache outside the repo, and symlinks the selected skill folders
into ~/.agents/skills (or the given targets). Every check runs before any link
changes, so a failing run leaves the targets as they were.

    uv run bootstrap.py                      # link into ~/.agents/skills
    uv run bootstrap.py --dry-run            # fetch and check, change no links
    uv run bootstrap.py --sources skills/sources.yaml --sources ../overlay/sources.yaml
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCES = REPO_ROOT / "skills" / "sources.yaml"
DEFAULT_TARGET = Path.home() / ".agents" / "skills"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SKILL_FILE = "SKILL.md"


class BootstrapError(Exception):
    """Raised when sources, upstream content or targets fail a check."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Source:
    """One third-party skill source, as declared in a sources.yaml file."""

    name: str
    repo: str
    stable: str
    roots: list[str]
    keep: list[str] | None
    hold: bool
    declared_in: Path


@dataclass
class Replacement:
    """A declared collision: when several sources offer `skill`, take the one from `use`."""

    skill: str
    use: str
    declared_in: Path


@dataclass
class Config:
    """The merged content of every sources.yaml file passed in."""

    backbone: str
    sources: dict[str, Source]
    replaces: list[Replacement]


@dataclass
class LinkPlan:
    """The changes needed to make one target directory match the effective skill set."""

    target: Path
    create: dict[str, Path] = field(default_factory=dict)
    update: dict[str, Path] = field(default_factory=dict)
    remove: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- config


def load_config(paths: list[Path]) -> Config:
    """
    Load and merge sources.yaml files, validating every field

    **Args**:
        **paths** (*list[Path]*): sources.yaml files; the first is normally this repo's, later ones overlays

    **Returns**:
        The merged configuration, with `lab` entries ignored

    **Examples**:
        >>> config = load_config(
        ...     paths=[Path("skills/sources.yaml"), Path("../overlay/sources.yaml")]
        ... )
        Source names must be unique across files and `backbone` must be declared
        exactly once. All problems are collected and raised together.
    """
    problems: list[str] = []
    backbones: list[tuple[str, Path]] = []
    sources: dict[str, Source] = {}
    declared: dict[str, Path] = {}
    replaces: list[Replacement] = []

    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            problems.append(f"{path}: cannot read: {error}")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path}: top level must be a mapping")
            continue

        if data.get("backbone") is not None:
            backbones.append((str(data["backbone"]), path))

        for name, entry in (data.get("sources") or {}).items():
            if name in declared:
                problems.append(
                    f"{path}: source '{name}' is already declared in {declared[name]}"
                )
                continue
            declared[name] = path
            source = parse_source(
                name=name,
                entry=entry,
                declared_in=path,
                problems=problems,
            )
            if source is not None:
                sources[name] = source

        for entry in data.get("replaces") or []:
            if not isinstance(entry, dict) or not {"skill", "use"} <= entry.keys():
                problems.append(
                    f"{path}: each replaces entry needs 'skill' and 'use', got {entry!r}"
                )
                continue
            replaces.append(
                Replacement(
                    skill=str(entry["skill"]),
                    use=str(entry["use"]),
                    declared_in=path,
                )
            )

    if len(backbones) != 1:
        where = ", ".join(f"{name} ({path})" for name, path in backbones) or "none"
        problems.append(
            f"exactly one backbone must be declared across all files, found: {where}"
        )
        backbone = ""
    else:
        backbone = backbones[0][0]
        if backbone not in declared:
            problems.append(f"backbone '{backbone}' is not a declared source")

    for name, source in sources.items():
        if name != backbone and source.keep is None:
            problems.append(f"{source.declared_in}: source '{name}' needs a keep list")

    if problems:
        raise BootstrapError(problems)
    return Config(backbone=backbone, sources=sources, replaces=replaces)


def parse_source(
    name: str,
    entry: object,
    declared_in: Path,
    problems: list[str],
) -> Source | None:
    """
    Turn one raw `sources:` entry into a Source, recording any problems

    **Args**:
        **name** (*str*): the source's key in the sources mapping
        **entry** (*object*): the raw YAML value for that key
        **declared_in** (*Path*): the file the entry came from, used in messages
        **problems** (*list[str]*): list that problems are appended to

    **Returns**:
        The parsed source, or None when the entry is unusable

    **Examples**:
        >>> parse_source(
        ...     name="pstack",
        ...     entry={"repo": "https://github.com/cursor/plugins", "stable": "2f87c85...", ...},
        ...     declared_in=Path("skills/sources.yaml"),
        ...     problems=problems,
        ... )
        A `stable` that isn't a full 40-character SHA, or any value still set to
        TODO, is reported even when the source is on hold.
    """
    where = f"{declared_in}: source '{name}'"
    if not isinstance(entry, dict):
        problems.append(f"{where}: must be a mapping")
        return None

    count_before = len(problems)
    repo = entry.get("repo")
    stable = str(entry.get("stable", ""))
    roots = entry.get("roots")
    keep = entry.get("keep")

    if not isinstance(repo, str) or not repo or repo == "TODO":
        problems.append(f"{where}: repo is missing")
    if not SHA_PATTERN.fullmatch(stable):
        problems.append(
            f"{where}: stable must be a full 40-character commit SHA, got '{stable}'"
        )
    if not isinstance(roots, list) or not roots or "TODO" in roots:
        problems.append(f"{where}: roots must be a non-empty list without TODO")
    elif any(
        Path(str(root)).is_absolute() or ".." in Path(str(root)).parts for root in roots
    ):
        problems.append(f"{where}: roots must be relative paths inside the repo")
    if keep is not None and (not isinstance(keep, list) or not keep):
        problems.append(f"{where}: keep must be a non-empty list when present")
    if str(entry.get("licence", "TODO")) == "TODO":
        problems.append(f"{where}: licence is not set")

    if len(problems) > count_before:
        return None
    return Source(
        name=name,
        repo=repo,
        stable=stable,
        roots=[str(root) for root in roots],
        keep=[str(skill) for skill in keep] if keep is not None else None,
        hold=bool(entry.get("hold", False)),
        declared_in=declared_in,
    )


# --------------------------------------------------------------------------- fetch


def default_cache_dir() -> Path:
    """
    Pick the per-user cache folder for fetched sources on this OS

    **Returns**:
        The folder that holds one checkout per source and commit

    **Examples**:
        >>> default_cache_dir()
        On Linux this is $XDG_CACHE_HOME/mloadout/sources (or ~/.cache/...), on
        macOS ~/Library/Caches/mloadout/sources, and on Windows
        %LOCALAPPDATA%\\mloadout\\cache\\sources.
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "mloadout" / "cache" / "sources"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "mloadout" / "sources"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "mloadout" / "sources"


def run_git(
    args: list[str],
    cwd: Path | None = None,
) -> str:
    """
    Run a git command non-interactively and return its standard output

    **Args**:
        **args** (*list[str]*): arguments after `git`
        **cwd** (*Path | None*): working directory, or None for the current one

    **Returns**:
        The command's standard output with surrounding whitespace removed

    **Examples**:
        >>> run_git(
        ...     args=["rev-parse", "HEAD"],
        ...     cwd=checkout,
        ... )
        Credential prompts are disabled, so sources must be fetchable anonymously
        (ADR 0001). Git LFS content is not downloaded.
    """
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BootstrapError([f"git {' '.join(args)} failed: {result.stderr.strip()}"])
    return result.stdout.strip()


def fetch_source(
    source: Source,
    cache_dir: Path,
) -> Path:
    """
    Make sure the cache holds a checkout of the source at its stable commit

    **Args**:
        **source** (*Source*): the source to fetch
        **cache_dir** (*Path*): the cache root

    **Returns**:
        The checkout folder, `<cache_dir>/<source>/<stable>`

    **Examples**:
        >>> checkout = fetch_source(
        ...     source=config.sources["superpowers"],
        ...     cache_dir=default_cache_dir(),
        ... )
        Only that one commit is fetched (depth 1). An existing checkout is reused
        after checking its HEAD; a partial one from an interrupted run is replaced.
    """
    checkout = cache_dir / source.name / source.stable
    if checkout.is_dir():
        try:
            if run_git(args=["rev-parse", "HEAD"], cwd=checkout) == source.stable:
                return checkout
        except BootstrapError:
            pass
        remove_tree(path=checkout)

    staging = checkout.with_name(f".{source.stable}.partial")
    if staging.exists():
        remove_tree(path=staging)
    staging.mkdir(parents=True)

    print(f"  fetching {source.name} @ {source.stable[:12]}", flush=True)
    run_git(args=["init", "--quiet", str(staging)])
    run_git(
        args=[
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "--no-tags",
            source.repo,
            source.stable,
        ],
        cwd=staging,
    )
    run_git(
        args=["-c", "advice.detachedHead=false", "checkout", "--quiet", "FETCH_HEAD"],
        cwd=staging,
    )
    head = run_git(args=["rev-parse", "HEAD"], cwd=staging)
    if head != source.stable:
        raise BootstrapError(
            [f"{source.name}: fetched {head}, expected {source.stable}"]
        )
    staging.rename(checkout)
    return checkout


def remove_tree(path: Path) -> None:
    """
    Delete a cache folder, including git's read-only object files

    **Args**:
        **path** (*Path*): a folder inside the cache, never a link target

    **Returns**:
        Nothing

    **Examples**:
        >>> remove_tree(path=cache_dir / "pstack" / ".2f87c85...partial")
        Read-only files (which git creates and Windows refuses to delete) are made
        writable first.
    """

    def make_writable_and_retry(function, failed_path, _excinfo):
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(path, onexc=make_writable_and_retry)


# --------------------------------------------------------------------------- select


def select_skills(
    source: Source,
    checkout: Path,
    is_backbone: bool,
) -> dict[str, Path]:
    """
    Find the skill folders a source contributes, after its keep list is applied

    **Args**:
        **source** (*Source*): the source whose roots and keep list apply
        **checkout** (*Path*): the source's checkout in the cache
        **is_backbone** (*bool*): whether the source is all-on within its roots

    **Returns**:
        A mapping from skill name to skill folder

    **Examples**:
        >>> select_skills(
        ...     source=config.sources["mattpocock"],
        ...     checkout=checkout,
        ...     is_backbone=True,
        ... )
        For the backbone every direct subfolder of a root that holds a SKILL.md is
        taken. For other sources each keep name must exist in exactly one root.
        Every selected SKILL.md must name its own folder in its frontmatter.
    """
    problems: list[str] = []
    found: dict[str, list[Path]] = {}

    for root in source.roots:
        root_dir = checkout / root
        if not root_dir.is_dir():
            problems.append(
                f"{source.name}: root '{root}' does not exist at {source.stable[:12]}"
            )
            continue
        for skill_dir in sorted(root_dir.iterdir()):
            if skill_dir.is_dir() and (skill_dir / SKILL_FILE).is_file():
                found.setdefault(skill_dir.name, []).append(skill_dir)

    wanted = sorted(found) if is_backbone else (source.keep or [])
    selected: dict[str, Path] = {}
    for name in wanted:
        locations = found.get(name, [])
        if not locations:
            problems.append(
                f"{source.name}: keep name '{name}' no longer exists upstream "
                f"(roots {source.roots} at {source.stable[:12]})"
            )
        elif len(locations) > 1:
            listed = ", ".join(str(path.relative_to(checkout)) for path in locations)
            problems.append(
                f"{source.name}: skill '{name}' is in more than one root: {listed}"
            )
        else:
            problem = check_frontmatter(skill_dir=locations[0])
            if problem:
                problems.append(f"{source.name}: {problem}")
            selected[name] = locations[0]

    if problems:
        raise BootstrapError(problems)
    return selected


def check_frontmatter(skill_dir: Path) -> str | None:
    """
    Check that a SKILL.md has frontmatter naming its folder and carrying a description

    **Args**:
        **skill_dir** (*Path*): the skill folder

    **Returns**:
        A problem description, or None when the frontmatter is fine

    **Examples**:
        >>> check_frontmatter(skill_dir=checkout / "skills" / "tdd")
        Returns None for a SKILL.md starting with `---`, `name: tdd`,
        `description: ...`, `---`. Tools key skills by name, so a mismatch
        would install under a different name than the folder suggests.
    """
    text = (skill_dir / SKILL_FILE).read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---\r?\n(.*?)\r?\n---\s*(\r?\n|$)", text, flags=re.DOTALL)
    if not match:
        return f"{skill_dir.name}/{SKILL_FILE} has no frontmatter"
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as error:
        return f"{skill_dir.name}/{SKILL_FILE} frontmatter does not parse: {error}"
    if not isinstance(meta, dict):
        return f"{skill_dir.name}/{SKILL_FILE} frontmatter is not a mapping"
    if meta.get("name") != skill_dir.name:
        return f"{skill_dir.name}/{SKILL_FILE} names itself '{meta.get('name')}'"
    if not meta.get("description"):
        return f"{skill_dir.name}/{SKILL_FILE} has no description"
    return None


def resolve_collisions(
    selections: dict[str, dict[str, Path]],
    replaces: list[Replacement],
) -> dict[str, Path]:
    """
    Merge every source's selection into one effective set, applying `replaces`

    **Args**:
        **selections** (*dict[str, dict[str, Path]]*): skill folders per source name
        **replaces** (*list[Replacement]*): declared collisions and their winners

    **Returns**:
        A mapping from skill name to the one folder that gets linked

    **Examples**:
        >>> resolve_collisions(
        ...     selections={"mattpocock": {...}, "pstack": {...}},
        ...     replaces=[Replacement(skill="code-review", use="pstack", declared_in=...)],
        ... )
        An undeclared collision fails, and so does a replaces entry that no longer
        matches a collision, or names a source that doesn't offer the skill.
    """
    offered: dict[str, dict[str, Path]] = {}
    for source_name, skills in selections.items():
        for skill, path in skills.items():
            offered.setdefault(skill, {})[source_name] = path

    problems: list[str] = []
    winners: dict[str, str] = {}
    for replacement in replaces:
        where = f"{replacement.declared_in}: replaces '{replacement.skill}'"
        providers = offered.get(replacement.skill, {})
        if replacement.skill in winners:
            problems.append(f"{where}: declared more than once")
        elif len(providers) < 2:
            problems.append(
                f"{where}: no collision to resolve (offered by {sorted(providers)})"
            )
        elif replacement.use not in providers:
            problems.append(
                f"{where}: '{replacement.use}' is not one of {sorted(providers)}"
            )
        else:
            winners[replacement.skill] = replacement.use

    effective: dict[str, Path] = {}
    for skill, providers in sorted(offered.items()):
        if len(providers) == 1:
            effective[skill] = next(iter(providers.values()))
        elif skill in winners:
            effective[skill] = providers[winners[skill]]
        else:
            problems.append(
                f"skill '{skill}' is offered by {sorted(providers)}; "
                "add a replaces entry or drop it from a keep list"
            )

    if problems:
        raise BootstrapError(problems)
    return effective


# --------------------------------------------------------------------------- link


def link_destination(path: Path) -> Path | None:
    """
    Read where a symlink or Windows junction points

    **Args**:
        **path** (*Path*): an entry in a target directory

    **Returns**:
        The absolute destination, or None when the entry is not a link

    **Examples**:
        >>> link_destination(path=Path.home() / ".agents/skills/tdd")
        Windows' `\\\\?\\` prefix is stripped so paths compare equal to cache paths.
    """
    if not (path.is_symlink() or path.is_junction()):
        return None
    raw = os.readlink(path)
    raw = raw.removeprefix("\\\\?\\")
    destination = Path(raw)
    if not destination.is_absolute():
        destination = path.parent / destination
    return Path(os.path.normpath(destination))


def plan_links(
    target: Path,
    effective: dict[str, Path],
    cache_dir: Path,
) -> LinkPlan:
    """
    Work out which links to create, update and remove in one target directory

    **Args**:
        **target** (*Path*): the directory tools read skills from
        **effective** (*dict[str, Path]*): skill name to folder, from resolve_collisions
        **cache_dir** (*Path*): the cache root; links into it are owned by this script

    **Returns**:
        The plan for this target

    **Examples**:
        >>> plan = plan_links(
        ...     target=Path.home() / ".agents" / "skills",
        ...     effective=effective,
        ...     cache_dir=default_cache_dir(),
        ... )
        Only links into the cache are touched. A real folder or a foreign link
        with a wanted name is a conflict and fails the run.
    """
    plan = LinkPlan(target=target)
    cache_root = Path(os.path.normpath(cache_dir.resolve()))
    problems: list[str] = []

    existing: dict[str, Path | None] = {}
    if target.is_dir():
        for entry in target.iterdir():
            existing[entry.name] = link_destination(path=entry)

    for name, destination in existing.items():
        owned = destination is not None and destination.is_relative_to(cache_root)
        if name in effective:
            wanted = Path(os.path.normpath(effective[name].resolve()))
            if not owned:
                problems.append(
                    f"{target / name} exists and was not created by bootstrap; move it away first"
                )
            elif destination == wanted:
                plan.unchanged.append(name)
            else:
                plan.update[name] = wanted
        elif owned:
            plan.remove.append(name)

    for name, path in effective.items():
        if name not in existing:
            plan.create[name] = Path(os.path.normpath(path.resolve()))

    if problems:
        raise BootstrapError(problems)
    return plan


def make_dir_link(
    link: Path,
    destination: Path,
) -> None:
    """
    Create a directory symlink, falling back to a junction on Windows

    **Args**:
        **link** (*Path*): the link to create
        **destination** (*Path*): the folder it points to

    **Returns**:
        Nothing

    **Examples**:
        >>> make_dir_link(
        ...     link=Path.home() / ".agents/skills/tdd",
        ...     destination=checkout / "skills/engineering/tdd",
        ... )
        Windows only allows symlinks with Developer Mode or admin rights; without
        them a directory junction is made instead, which tools follow the same way.
    """
    try:
        os.symlink(destination, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi

        _winapi.CreateJunction(str(destination), str(link))


def remove_link(link: Path) -> None:
    """
    Remove a symlink or junction without touching what it points to

    **Args**:
        **link** (*Path*): the link to remove

    **Returns**:
        Nothing

    **Examples**:
        >>> remove_link(link=Path.home() / ".agents/skills/old-skill")
        On Windows directory links are removed with rmdir, which deletes the link only.
    """
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


def apply_plan(plan: LinkPlan) -> None:
    """
    Carry out a link plan

    **Args**:
        **plan** (*LinkPlan*): the plan from plan_links

    **Returns**:
        Nothing

    **Examples**:
        >>> apply_plan(plan=plan)
        Removals and updates happen before creations; the target folder is
        created if it doesn't exist.
    """
    plan.target.mkdir(parents=True, exist_ok=True)
    for name in plan.remove:
        remove_link(link=plan.target / name)
    for name, destination in plan.update.items():
        remove_link(link=plan.target / name)
        make_dir_link(link=plan.target / name, destination=destination)
    for name, destination in plan.create.items():
        make_dir_link(link=plan.target / name, destination=destination)


def print_plan(
    plan: LinkPlan,
    dry_run: bool,
) -> None:
    """
    Print what a plan changes in its target

    **Args**:
        **plan** (*LinkPlan*): the plan to describe
        **dry_run** (*bool*): whether the changes are only being previewed

    **Returns**:
        Nothing

    **Examples**:
        >>> print_plan(plan=plan, dry_run=True)
        Lists each created (+), updated (~) and removed (-) link, then a count
        of unchanged ones.
    """
    verb = "would change" if dry_run else "changed"
    changes = len(plan.create) + len(plan.update) + len(plan.remove)
    print(f"\n{plan.target}: {verb} {changes}, unchanged {len(plan.unchanged)}")
    for name in sorted(plan.create):
        print(f"  + {name}")
    for name in sorted(plan.update):
        print(f"  ~ {name}")
    for name in sorted(plan.remove):
        print(f"  - {name}")


# --------------------------------------------------------------------------- main


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    Parse the command line

    **Args**:
        **argv** (*list[str] | None*): arguments, or None to read sys.argv

    **Returns**:
        The parsed options

    **Examples**:
        >>> parse_args(argv=["--dry-run", "--target", "~/.claude/skills"])
        `--sources` and `--target` can be repeated; each defaults to this repo's
        sources.yaml and ~/.agents/skills when not given.
    """
    parser = argparse.ArgumentParser(
        description="Link pinned Agent Skills into the shared skills directory (ADR 0002).",
    )
    parser.add_argument(
        "--sources",
        action="append",
        type=Path,
        help=f"a sources.yaml file; repeat for overlays (default: {DEFAULT_SOURCES})",
    )
    parser.add_argument(
        "--target",
        action="append",
        type=lambda value: Path(value).expanduser(),
        help=f"directory to link skills into; repeat for fallbacks (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--cache-dir",
        type=lambda value: Path(value).expanduser(),
        default=default_cache_dir(),
        help="where sources are fetched (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and check everything, but change no links",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Run the bootstrap end to end

    **Args**:
        **argv** (*list[str] | None*): command-line arguments, or None to read sys.argv

    **Returns**:
        The process exit code: 0 on success, 1 when a check fails

    **Examples**:
        >>> main(argv=["--dry-run"])
        Load and validate config, fetch sources, select skills, resolve collisions,
        plan every target, and only then change links.
    """
    args = parse_args(argv=argv)
    sources_files = args.sources or [DEFAULT_SOURCES]
    targets = args.target or [DEFAULT_TARGET]

    try:
        config = load_config(paths=sources_files)
        active = {
            name: source for name, source in config.sources.items() if not source.hold
        }
        for name, source in config.sources.items():
            if source.hold:
                print(
                    f"  holding {name} (hold: true in {source.declared_in})", flush=True
                )

        selections: dict[str, dict[str, Path]] = {}
        problems: list[str] = []
        for name, source in active.items():
            try:
                checkout = fetch_source(source=source, cache_dir=args.cache_dir)
                selections[name] = select_skills(
                    source=source,
                    checkout=checkout,
                    is_backbone=name == config.backbone,
                )
            except BootstrapError as error:
                problems.extend(error.problems)
        if problems:
            raise BootstrapError(problems)

        effective = resolve_collisions(selections=selections, replaces=config.replaces)
        plans = [
            plan_links(target=target, effective=effective, cache_dir=args.cache_dir)
            for target in targets
        ]
    except BootstrapError as error:
        print("bootstrap failed; no links were changed:", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    for plan in plans:
        if not args.dry_run:
            apply_plan(plan=plan)
        print_plan(plan=plan, dry_run=args.dry_run)

    counts = ", ".join(f"{name} {len(skills)}" for name, skills in selections.items())
    print(f"\n{len(effective)} skills from {len(selections)} sources ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
