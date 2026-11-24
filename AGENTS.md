# AGENTS.md

mloadout links pinned third-party Agent Skills into `~/.agents/skills` (see README.md). The repo is public.

## Rules

- **Public and generic only** ([ADR 0001](docs/adr/0001-public-generic-only.md)): everything committed here could sit on any machine and in any company. Employer names, hosts, internal URLs and credentials belong in the employer's overlay repo.
- **Third-party skill files stay in the cache.** This repo holds only `skills/sources.yaml`, which names them; bootstrap fetches them.
- **`skills/sources.yaml`**: `stable` is always a full 40-character commit SHA. Bumping `stable` needs no ADR. Adding or dropping a source does: write one in `docs/adr/` first.
- **Bootstrap's command-line interface is a contract** with the overlay repo. Treat renaming or removing an option as a breaking change (`!` plus a `BREAKING CHANGE:` footer).

## Before changing design

Read the ADR that covers the area before changing the code:

- `docs/adr/0002-agent-skills-not-plugins.md`: source format, selection, collisions, bootstrap behaviour and its options.
- `docs/adr/0003-blind-comparison-for-skill-updates.md`: how a `stable` bump or a rival skill gets evaluated.

When a change departs from an ADR, update that ADR in the same branch.

## Verify

- `uv run pytest`: offline, uses local git repos as fake upstreams.
- `uv run mloadout bootstrap --dry-run`: the real sources, no links changed.

If `uv` warns that `VIRTUAL_ENV` doesn't match, it's coming from another project's shell. Run `unset VIRTUAL_ENV` first.

## Commits

Every commit message follows [`.gitmessage`](.gitmessage): Conventional Commits, an imperative lower-case subject of at most 72 characters, a body that says why, and the footers it lists. Read it before your first commit in a session. One logical change per commit.

## Releases

The version lives only in `pyproject.toml`; `mloadout.__version__` reads it from package metadata. After changing it, run `uv lock` and commit `uv.lock` together with `pyproject.toml`.
