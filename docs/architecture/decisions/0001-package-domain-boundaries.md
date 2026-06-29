# Package Domain Boundaries

The package-domain refactor moves the previously flat `codex_usage_tracker` source tree into responsibility folders and switches Tach from one large root module list to per-domain `tach.domain.toml` files.

The initial domain policy declares dependencies that match the current implementation after the move. Circular dependency blocking remains disabled because the existing parser, diagnostics, and store flow still has a real cycle: parser state feeds diagnostic facts, diagnostics snapshots read persisted state, and store helpers import parser state metadata. That cycle is preserved for behavior compatibility and should be reduced in a later, focused branch.

This is an architecture policy change, not an attempt to bypass drift: the old Tach module paths no longer exist after the file move, and per-domain files give each responsibility folder local ownership of its boundary declaration.
