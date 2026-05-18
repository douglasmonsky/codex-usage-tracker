# Security Policy

## Supported Versions

Security fixes target the latest release on `main`.

## Reporting A Vulnerability

Open a private GitHub security advisory when this repository is public and advisories are enabled. Until then, contact the maintainer directly.

## Data Boundary

Codex Usage Tracker is designed to index aggregate token metadata from local Codex logs. Reports, CSV exports, dashboards, and the SQLite database must not contain raw prompts, assistant text, tool outputs, pasted secrets, or transcript snippets.

The optional localhost context endpoint reads one selected source JSONL record on demand, redacts common secret patterns, caps returned text size, and does not persist the loaded context.
