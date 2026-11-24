# 0001: Keep this repo public and generic-only

- **Status:** accepted
- **Date:** 2026-11-18

## Context

My setup spans personal machines and employer-managed environments. Employer-specific configuration and content must never end up outside the employer, and personal credentials should never need to live on employer machines.

## Decision

This repo holds only generic setup and is public. Employer-specific configuration lives in a separate, employer-owned overlay repo that clones this one read-only and applies its own layer on top.

## Consequences

- Work environments clone anonymously over HTTPS, so no personal credentials sit on employer machines.
- Being public forces discipline about what goes in.
- Guardrails (Gitleaks plus an out-of-repo denylist) are mandatory on every machine I commit from.
- Two repos have to stay compatible: the overlay depends on this repo's bootstrap interface.

## Alternatives considered

- **Everything in the employer's repo.** Simplest, but the generic setup can't be used elsewhere and leaves with the job.
- **Private personal repo.** Needs personal credentials on employer machines, which is exactly the conflation to avoid.
