# 0003: Promote skill updates by gated, blind comparison

- **Status:** accepted
- **Date:** 2026-11-19

## Context

ADR 0002 pins every third-party skill source to a stable commit and fetches upstream HEAD as a candidate. I want to decide whether to move to the candidate from evidence, not from reading diffs. I also want the same process to choose between rival skills from different sources that do the same job, such as two debugging skills.

A model that scores outputs checks quality, not intent: it will pass a well-behaved update that also adds a harmful instruction. It also reads text derived from the candidate, which makes it an injection target. A judge that knows which output came from which model, version or source is biased.

## Decision

Every candidate, whether a newer commit of a source or a rival skill, goes through four steps.

### 1. Fixed security check

Before any model sees the candidate, a deterministic check compares candidate with stable and flags:

- new or changed files outside `SKILL.md`, especially scripts, binaries and installers;
- new URLs or domains;
- instructions that mention home-directory config (`~/.claude`, `~/.config`, agent instruction files), credentials, tokens or piped installers;
- any frontmatter change, especially to `disable-model-invocation`;
- new skill folders.

Any flag stops the pipeline until I have reviewed it by hand.

### 2. Scenario runs

- A fixed set of scenarios (a prompt, a small fixture repo, a rubric) is run once with stable and once with the candidate.
- The runner works with any agent: its core knows nothing about specific tools, and each agent CLI (e.g. Copilot CLI `-p`, `opencode run`) is a small adapter.
- Runs happen in a short-lived environment with no cloud, data-platform or issue-tracker credentials.

### 3. Blind judging

- The scoring model must differ from every model that produced an output in the comparison.
- Outputs are given pseudonyms: random labels and a random order per scenario. Model, skill, source and version names are removed from the outputs and their metadata.
- The runner keeps the mapping from pseudonym to version and reveals it only after the verdict.
- The judge scores against the scenario's rubric, has no tools, and sees only the pseudonymised outputs and the rubric.

### 4. Record and decide

- Each comparison stores the scenarios, the stable and candidate SHAs, the producing models, the judge model, the pseudonym mapping, the rubric scores and the verdict.
- I make the final call. Promoting means moving `stable` in `sources.yaml`, with a link to the record.

### Where things live and run

- The runner and the generic scenarios live in this repo and run on a personal machine.
- Scenarios built on employer code live in the employer overlay. They run in a separate, short-lived employer workspace with no credentials, using the same runner.

## Consequences

- Updates and rival skills are decided on evidence, and every decision leaves a record.
- It costs tokens and time, and scenarios take effort to write. Start with a few scenarios per skill I actually use, and add more as I go.
- Recording the judge model keeps results honest when the judge changes: scores from different judges aren't directly comparable.
- Random order reduces the judge's bias towards one position. Pseudonyms reduce bias towards a model, version or source.
- Outputs can still echo candidate text into the judge. The fixed check comes first and the judge has no tools, which limits the damage, but it doesn't remove the risk. That's why the final decision stays with me.
- An employer workspace without credentials has to exist and be cheap to create. That depends on Coder templates.

## Alternatives considered

- **Reading text diffs only.** Cheap, but it can't show how a change behaves.
- **Following upstream live.** Rejected in ADR 0002.
- **Judging by hand only.** Unbiased by model, but too slow to do regularly, and biased by what I expect to see.
- **A judge that sees labels.** Rejected: it invites bias towards the model, version or source.
- **Running candidates in the everyday work workspace.** Rejected: that workspace holds real credentials.
