# R8 — Publish Public Product Documentation

## Objective

Turn the repository front door into an inviting, accurate explanation of a
mature community product, using only claims and visuals proven by R6 and R7.

## Depends On

R0 starts the durable copy audit. R8 completes only after R6 and R7.

## Owned Areas

- `README.md`
- user documentation home and getting-started guide;
- copy-paste questions and conversation examples;
- Console, CLI, MCP, and query references;
- troubleshooting and privacy documentation;
- `SECURITY.md`, `CONTRIBUTING.md`, issue templates, and public metadata;
- final synthetic screenshots.

The paused `docs/public-product-docs` draft is input, not an automatic merge.

## Contract Added First

Add failing public-document checks for:

- current installable version and source;
- agent-install prompt;
- six-tool surface;
- fresh-task requirement;
- performance and refresh semantics;
- metadata-only privacy;
- exact/estimated/inference wording;
- valid local links;
- synthetic screenshot provenance;
- no retired commands or product surfaces.

## Required Front Door

The README leads with:

- what the product helps a person understand;
- one strong Console visual;
- “Want your agent to set it up for you?” copy-paste prompt;
- manual installation;
- first useful question;
- realistic conversation examples;
- local-first trust boundary;
- community and contribution paths.

It must not lead with internal roadmap mechanics, frozen contracts, or
repository architecture.

## Required Guides

- documentation home;
- install and first run;
- what to ask Codex;
- worked conversations;
- Console guide;
- MCP reference;
- CLI reference;
- query and evidence reference;
- cost, credits, allowance, and coverage;
- performance and troubleshooting;
- privacy and safe issue reporting;
- upgrade to `0.29.0`.

## Screenshots And Conversations

- Capture the final shipped Console through deterministic synthetic fixtures.
- Show Live, Explore, Evidence, and Limits.
- Use human thread names and qualified metrics.
- Do not include local paths, real usage, prompts, tools, projects, or labels.
- Conversation examples use R7 synthetic outcomes and are edited for clarity
  without inventing capability or timing.

## Parallel Execution

An explicitly authorized documentation subagent may audit stale public claims
after R0 while R3–R7 continue. It owns documentation-only files and produces a
replacement list, not final performance claims or screenshots.

After R6 and R7, separate subagents may draft:

- installation and troubleshooting;
- conversation examples and product recipes;
- reference documentation.

The R8 coordinator owns README voice, cross-document consistency, screenshots,
version wording, and final integration. No two agents edit README or the same
guide concurrently.

## Validation

- public-doc contract tests;
- Markdown and local-link checks;
- release metadata checks;
- screenshot visual inspection;
- synthetic-data provenance;
- install command verification;
- fresh-task example replay;
- stale-surface search;
- build and installed-package docs smoke.

## Acceptance

- A new user understands value before architecture.
- Agent and manual installation are copy-pastable and current.
- Examples match qualified behavior.
- Screenshots show the final product.
- Privacy and estimation caveats are clear without overwhelming the pitch.
- No unshipped or retired surface is advertised.

## Handoff

R9 receives release-ready docs with version placeholders resolved only on the
release branch.
