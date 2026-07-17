# Persistent Dashboard Service Design

## Goal

Give the local dashboard one memorable address and keep it available across
Codex tasks, terminal exits, crashes, and Mac logins. The default address is
`http://127.0.0.1:47821`.

The IP address is deliberately loopback-only. Port `47821` is preferred over
the existing interactive default, `8765`, because `8765` is registered by IANA
for Ultraseek HTTP and is commonly used by development servers. Port `47821`
is not assigned in the IANA service registry, was unused on the target Mac at
design time, and is below that Mac's `49152-65535` ephemeral range.

## Approaches Considered

### macOS LaunchAgent (selected)

A user LaunchAgent starts the existing dashboard server at login and restarts
it after an unexpected exit. This is native to macOS, survives terminal and
Codex task lifetimes, requires no privileged system service, and can remain
strictly bound to localhost.

### Detached terminal process

This is easy to start but does not reliably survive logout or reboot, has no
standard status interface, and tends to leave users unsure which process owns
the port.

### Codex-started background process

Starting the server when Codex opens still couples dashboard availability to
Codex and makes duplicate-process handling harder. It does not solve the
request for an independently persistent local address.

## User Interface

Add a nested CLI command with three actions:

```text
codex-usage-tracker dashboard-service install [--port 47821]
codex-usage-tracker dashboard-service status
codex-usage-tracker dashboard-service uninstall
```

`install` creates or updates the user LaunchAgent, loads it, and prints the
fixed dashboard URL. It does not open a browser tab. `status` reports whether
the agent is installed, loaded, running, and reachable, followed by the URL or
a concise recovery instruction. `uninstall` unloads the managed agent and
removes only the plist created by this feature.

The first release is intentionally macOS-only. On another operating system,
all three actions return a clear unsupported-platform error without writing
files. Linux systemd support can be added separately if a concrete need
appears.

## Components and Responsibilities

### CLI parser and dispatcher

The existing argparse CLI owns command discovery and dispatch. It validates
the action and port, then delegates to a dashboard-service module. Service
lifecycle logic does not belong in the dashboard HTTP server.

### Dashboard-service module

A focused module owns:

- service paths and the stable LaunchAgent label;
- deterministic plist construction;
- target-port availability checks;
- `launchctl` invocation through argument arrays, never shell strings;
- atomic installation of the generated plist;
- service status and localhost HTTP reachability checks; and
- safe removal of the package-managed plist.

The LaunchAgent label is `com.codex-usage-tracker.dashboard`. Its plist lives
at `~/Library/LaunchAgents/com.codex-usage-tracker.dashboard.plist`. Logs live
under `~/.codex-usage-tracker/logs/` and contain process diagnostics only; the
service must not log prompts, raw context, or usage records.

### LaunchAgent process

The generated plist records the absolute Python interpreter used to run the
install command and launches:

```text
python -m codex_usage_tracker serve-dashboard
  --host 127.0.0.1
  --port 47821
  --context-api explicit
```

The actual plist stores these as separate `ProgramArguments`. It uses
`RunAtLoad` and `KeepAlive`, sets a restart throttle, supplies an explicit
`HOME`, and does not inject secrets or broaden network access. The browser-open
flag is omitted.

Using the install-time interpreter avoids relying on launchd's minimal `PATH`.
If that interpreter later disappears, `status` explains that the service must
be reinstalled from the current package environment.

## Lifecycle and Data Flow

1. `install` validates macOS, the interpreter, destination directories, and
   the requested port.
2. If an unknown process owns the requested port, installation fails and
   reports the collision. It never kills an unknown process and never silently
   chooses a different port.
3. The command writes the deterministic plist atomically, then bootstraps the
   LaunchAgent in the current user's `gui/<uid>` domain.
4. launchd starts the existing localhost dashboard server and restarts it when
   needed.
5. The dashboard continues using its existing explicit refresh and lazy
   context-loading behavior. Persistence does not introduce background log
   polling beyond behavior already performed by `serve-dashboard`.
6. `status` combines launchd state with a bounded HTTP probe so a loaded but
   unreachable process is distinguishable from a healthy service.

Installation is idempotent. Re-running it updates the managed plist and
restarts only the managed LaunchAgent. A port is not literally reserved while
the service is stopped; while the agent is active, the server's loopback bind
holds it. The collision checks and fixed configuration make failures explicit
rather than changing the URL.

## Error Handling

- Invalid or privileged ports fail before filesystem or launchd mutation.
- A target-port collision names the port and asks the user to stop the owner or
  reinstall with an explicit alternative.
- Missing `launchctl`, an invalid user domain, plist write failures, bootstrap
  failures, and failed health probes produce distinct concise messages.
- A failed install preserves any previously valid managed plist whenever
  possible; atomic replacement prevents partial configuration files.
- Uninstall is idempotent when the service or plist is already absent.
- Status is read-only and does not attempt automatic repair.

## Privacy and Security

- The server remains bound to `127.0.0.1`; the service interface does not offer
  a non-loopback host option.
- Existing explicit raw-context controls remain unchanged.
- The plist contains only executable paths, fixed arguments, HOME, and log
  paths. It contains no credentials, session content, database rows, or copied
  allowance data.
- Generated logs and service state remain local and are excluded from package
  and repository artifacts.

## Verification

Implementation follows test-driven development. Tests use temporary homes,
synthetic inputs, fake subprocess results, and local disposable sockets; they
must not load or modify the developer's real LaunchAgent during the automated
suite.

Coverage includes:

- parser and dispatch behavior for all three actions;
- deterministic, valid plist generation with localhost-only arguments;
- default and overridden port validation;
- collision refusal without killing or replacing an unknown listener;
- idempotent install and uninstall flows;
- launchctl error translation and missing-interpreter reporting;
- status distinctions for absent, loaded, running, and HTTP-reachable states;
- unsupported-platform behavior; and
- privacy assertions preventing secrets or raw content in plist/log settings.

Focused service tests run first. Because this changes a CLI surface, packaged
behavior, dashboard startup, and user documentation, the repository's full
local CI and release-readiness gates run before the branch is considered
complete.

## Documentation and Rollout

Update the install guide, dashboard guide, CLI reference, and bundled tracker
skill with the fixed URL and lifecycle commands. Keep `serve-dashboard` and its
existing default port backward-compatible for interactive users; only the new
persistent service defaults to `47821`.

After implementation and verification, install the service for the current
user, confirm `status` reports it reachable, and probe
`http://127.0.0.1:47821`. The currently running interactive server on `8765`
is not killed automatically; it may exit naturally without affecting the new
service.
