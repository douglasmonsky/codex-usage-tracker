# First Five Minutes

This is the shortest path from a fresh machine to a grounded MCP answer with
optional local evidence.

## 1. Install

Use `pipx` so the tracker runs as its own command-line app:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install codex-usage-tracking
```

Use `python3` on macOS/Linux if that is your normal launcher. On Windows,
`py -m pip install --user pipx` and `py -m pipx ensurepath` may be the right
form. If `codex-usage-tracker` is not found, open a new terminal or add the path
printed by `pipx ensurepath`.

## 2. Set Up

```bash
codex-usage-tracker setup
```

`setup` installs the local Codex plugin wrapper, initializes local config
templates, performs the normal refresh of aggregate counters and the bounded
local content/event index, and runs `doctor`.

## 3. Restart Or Open A Fresh Task

Follow the setup result. Restart Codex or open a fresh task when instructed so
the plugin and MCP tools can be discovered. A healthy local installation does
not prove that a task created earlier exposes those tools.

## 4. Ask A Starter Question

In the fresh task, ask:

```text
What drove my Codex usage this week? State the scope and limitations, and link
the evidence behind each material conclusion.
```

The agent should use MCP tools for deterministic local analysis. If MCP is not
available in the current task, run:

```bash
codex-usage-tracker doctor --suggest-repair
```

Then follow its recovery guidance. CLI JSON commands remain available for local
automation and recovery.

## 5. Optionally Open Evidence

When an MCP result includes an Evidence Console target, open its absolute
localhost URL when present. If it includes only a relative target and launch
guidance, run:

```bash
codex-usage-tracker serve-dashboard --open
```

Then follow the relative target. The Evidence Console supports verification; it
is not required to receive the first useful answer.

## If There Is No Usage Yet

No result may simply mean that the machine has no local Codex logs. Confirm the
configured paths and refresh state:

```bash
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker refresh
```

If logs are outside `~/.codex`, pass `--codex-home <path>` to `setup` or
`refresh`. Use `--include-archived` only when older archived history is relevant.

## What To Attach To Issues

For public GitHub issues, prefer a strict support bundle:

```bash
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

Review the JSON before posting it. Do not attach raw Codex JSONL logs, prompts,
assistant messages, tool output, command text, patch text, full local paths,
secrets, credentials, or private config values.

For deeper details, see the [Install Guide](install.md),
[MCP And Codex Skills](mcp.md), [Evidence Console](evidence-console.md),
[Data Posture](data-posture.md), and [CLI Reference](cli-reference.md).
