# 0002: Skills are plain Agent Skills folders, linked into one directory from pinned sources

- **Status:** accepted 2026-11-19. Rollout to work environments waits on the verification items below.
- **Date:** 2026-11-18, revised 2026-11-19

## Context

I use several AI tools across several machines, and the set changes. Each tool has its own plugin, extension or marketplace. Maintaining a plugin per tool means one packaging format, one update path and one drifting copy of each skill per tool.

Agent Skills (a folder with a `SKILL.md` carrying `name` and `description` frontmatter) is an open standard. GitHub Copilot in VS Code reads personal skills from `~/.copilot/skills/`, `~/.claude/skills/` and `~/.agents/skills/`. opencode reads global skills from `~/.config/opencode/skills/`, `~/.claude/skills/` and `~/.agents/skills/`. `~/.agents/skills/` is the shared, vendor-neutral path.

Third-party bundles are worth using but churn hard: skills are renamed, removed and rewritten every few weeks. They are also a supply-chain risk. A November 2026 scan of the 20,000 most-installed public skills found 18 malicious ones, one of which rewrote the user's global agent instructions. Self-updating plugins pull such changes in without review.

## Decision

### Format and install target

- Every skill is a plain Agent Skills folder, `<name>/SKILL.md`, with frontmatter limited to the standard fields.
- Bootstrap symlinks each skill folder into `~/.agents/skills/<name>`. That is the single install target. A tool that can't read it gets a link to the same folder, never a copy.
- I never maintain plugins. A third-party plugin is allowed only as a fallback where the tool has no filesystem (Claude chat). My own skills reach Claude chat as a zip built from the same folders.

### Sources

- Third-party sources are listed in `skills/sources.yaml` in this repo. Overlay repos keep their own `sources.yaml` for sources internal to them only.
- Each entry has: `repo`, `stable` (full 40-character commit SHA), `roots` (folders inside the repo to read), an optional `keep` list, and `licence`.
- Third-party files are never committed here. Bootstrap fetches each source at its `stable` commit into a cache folder outside the repo and links from there.
- **Selection:** the backbone source is all-on within its declared `roots`. Every other source has a `keep` list from day one.

### Versions

- **Stable** is the pinned SHA, and it is the only version ever linked.
- **Candidate** is upstream HEAD. It is fetched into the cache for comparison only and never linked (process in ADR 0003).
- Moving `stable` to a newer commit is an update, not a promotion, and needs no ADR; the comparison record is its evidence. Adding or dropping a source needs an ADR.

### Collisions and bootstrap checks

- Name collisions are checked on the effective set, after keep-lists are applied. Any collision not declared with a `replaces:` entry fails the bootstrap.
- A `keep` name that no longer exists upstream fails the bootstrap.

### Initial sources

| Source | Repo | Selection |
|---|---|---|
| mattpocock (backbone) | `mattpocock/skills` | all-on within `skills/engineering`, `skills/productivity`; never `misc/` or `in-progress/` |
| pstack | `cursor/plugins` (upstream publisher), root `pstack/skills` | keep: unslop, technical-writing, bro, sharpen, blast-radius, benchmark-checklist |
| superpowers | `obra/superpowers` | keep: verification-before-completion, receiving-code-review |
| databricks | `databricks/databricks-agent-skills` | keep: ~10 core skills (DABs, pipelines, jobs, Unity Catalog, Python SDK, streaming, DBSQL, compute, docs, core); held until its licence is confirmed |

Lab only, used as challengers in ADR 0003 comparisons, never linked in production: superpowers `systematic-debugging` and `requesting-code-review`, github/awesome-copilot `azure-devops-cli`, trailofbits/skills `modern-python`, `differential-review`, `supply-chain-risk-auditor`.

No `replaces:` entries are needed at the start.

## Consequences

- One copy per skill, and for skills "render" reduces to linking. Assembling agent instructions (`AGENTS.md` etc.) is a separate decision.
- Adding a tool means checking that it reads `~/.agents/skills/`, not writing a plugin.
- Tool-specific frontmatter is off-limits, which gives up some per-tool features.
- Upstream renames break the bootstrap loudly. That is intended, and it creates upkeep.
- Superpowers runs without its session-start hook, a mode its maintainers don't support. Only standalone skills are taken from it for that reason.
- pstack skills are slash-only, so `unslop` and the others run when typed, not automatically.
- **Known risk, accepted:** Claude chat uses mattpocock's self-updating plugin, so it runs roughly upstream HEAD while production runs stable.
- **Accepted:** mattpocock's `/research` collides with built-in commands in some tools. Call it by description or by its namespaced form.
- mattpocock's tracker skills (`to-spec`, `to-tickets`, `triage`) stay unconfigured until an Azure DevOps tracker adapter exists in the overlay. That is deferred.
- Pinned sources go stale unless bumped through ADR 0003.
- Depends on tools continuing to honour the shared path. `~/.claude/skills/` and `~/.copilot/skills/` are the fallback link targets.

## Alternatives considered

- **Per-tool plugins.** Richest integration in each tool, but N formats and N update paths. Self-updating plugins also skip review.
- **Vendoring third-party skills into this repo.** Gives a reviewable copy, but adds noise and a second copy, and for CC-BY-SA sources it turns local edits into republishing.
- **Tracking upstream live.** Rejected: production behaviour would change without review.
- **Every source all-on.** Rejected: it pulls in frozen and beta skills, about 58 slash commands and a self-loading router, and it multiplies overlapping triggers.
- **Project-level skills only (`.agents/skills/` per repo).** Kept open for sharing with a team later. As the only mechanism, personal skills would have to be copied into every repo.

## To verify before rollout

- In a remote dev environment (Coder), VS Code with Copilot discovers skills from the workspace's `~/.agents/skills/` and follows symlinks.
- No organisation or enterprise policy disables agent skills.
- The installed opencode version reads `~/.agents/skills/` and respects `disable-model-invocation`.
- Copilot can carry out mattpocock's "call the Skill tool" step.
- The licence of every source, especially `databricks/databricks-agent-skills`.
