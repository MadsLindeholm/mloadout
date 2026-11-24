# mloadout

My generic, public dev setup. Right now it does one job: it installs a pinned set of [Agent Skills](https://agentskills.io) from third-party repos, so every AI coding tool on every machine sees the same reviewed copy of each skill.

Employer-specific setup never goes here. It lives in a separate overlay repo that builds on this one ([ADR 0001](docs/adr/0001-public-generic-only.md)).

## How it works

1. [`skills/sources.yaml`](skills/sources.yaml) lists each skill source: its repo, a pinned commit (`stable`), the folders to read and which skills to keep.
2. `mloadout bootstrap` fetches each source at that commit into a cache outside the repo (`~/.cache/mloadout/sources` on Linux).
3. It symlinks each selected skill folder into one shared directory, `~/.agents/skills/<name>`. Tools read the skills from there.

Nothing is copied or vendored, and nothing tracks upstream on its own. A skill changes only when its `stable` commit is bumped in `sources.yaml`. The full design is in [ADR 0002](docs/adr/0002-agent-skills-not-plugins.md), and how updates get evaluated is in [ADR 0003](docs/adr/0003-blind-comparison-for-skill-updates.md).

## Requirements

- git
- [uv](https://docs.astral.sh/uv/) (it provides Python 3.12+ if the machine lacks it)

## Install

```sh
uv tool install git+https://github.com/MadsLindeholm/mloadout@<commit>
```

Installing from a commit pins the bootstrap code the same way `stable` pins each skill source. The installed tool carries its own copy of `sources.yaml`, so a change to that file reaches a machine only after the tool is reinstalled at the new commit.

## Activate the skills

Link the skills into the shared directory, plus any tool that doesn't read it:

```sh
mloadout bootstrap --target ~/.agents/skills --target ~/.claude/skills
```

| Tool | Reads skills from |
|---|---|
| GitHub Copilot (VS Code) | `~/.agents/skills` (also `~/.copilot/skills`, `~/.claude/skills`) |
| opencode | `~/.agents/skills` (also `~/.config/opencode/skills`, `~/.claude/skills`) |
| Claude Code | `~/.claude/skills`, so add it with `--target` |

Each `--target` replaces the default, so list `~/.agents/skills` too when you add another. Start a new session in the tool so it picks up the skills.

Run with `--dry-run` first to fetch and check everything without changing any links. Bootstrap runs every check for every target before it touches a link, so a failed run leaves your directories as they were. It manages only links that point into its cache. A real folder or someone else's link with the same name counts as a conflict and stops the run.

### Options

| Option | Purpose |
|---|---|
| `--target <dir>` | Directory to link skills into. Repeatable. Default `~/.agents/skills`. |
| `--overlay <file>` | Extra `sources.yaml` whose sources are added to the base. Repeatable. Used by the employer overlay. |
| `--base <file>` | Use another `sources.yaml` in place of the bundled one, for testing a changed copy. |
| `--cache-dir <dir>` | Where sources are fetched. |
| `--dry-run` | Fetch and check, but change no links. |

`mloadout bootstrap --help` shows the current list.

## Sources

| Source | Selection |
|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) (backbone) | everything under `skills/engineering` and `skills/productivity` |
| [cursor/plugins](https://github.com/cursor/plugins) (pstack) | `unslop`, `technical-writing`, `bro`, `sharpen`, `blast-radius`, `benchmark-checklist` |
| [obra/superpowers](https://github.com/obra/superpowers) | `verification-before-completion`, `receiving-code-review` |
| [databricks/databricks-agent-skills](https://github.com/databricks/databricks-agent-skills) | 10 core skills, **on hold** until its licence terms are accepted |

The pinned commits and the exact lists live in [`skills/sources.yaml`](skills/sources.yaml). Bootstrap fails loudly if:

- a `keep` name no longer exists upstream
- two sources offer the same skill name and no `replaces:` entry picks one
- a `SKILL.md` has a `name` that doesn't match its folder

## Development

```sh
uv sync
uv run mloadout bootstrap --dry-run   # run the working copy
uv run pytest                          # offline; uses local git repos as fake upstreams
```

Commits follow Conventional Commits. Turn on the template once per clone:

```sh
git config commit.template .gitmessage
```

## Licence

Third-party skills are never committed here. Each one keeps its own licence, which is recorded per source in `sources.yaml`.
