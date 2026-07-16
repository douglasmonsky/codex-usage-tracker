# Windows Filesystem Identity Overflow Fix Design

**Issue:** [#278](https://github.com/douglasmonsky/codex-usage-tracker/issues/278)
**Status:** Approved

## Problem

`source_files.source_device` and `source_files.source_inode` were added to distinguish an appended source log from a replaced file. The current source metadata path converts both identifiers to Python integers and binds them directly into SQLite `INTEGER` columns.

On Windows with Python 3.12 or newer, `Path.stat().st_ino` may contain a 128-bit file identifier. Python's SQLite adapter rejects values outside the signed 64-bit SQLite integer range, so setup and refresh can fail with `OverflowError: Python int too large to convert to SQLite INTEGER`.

## Goals

- Preserve complete filesystem identifiers without truncation or hashing.
- Keep setup, full refresh, unchanged-source detection, and append-only parsing working on Windows, macOS, and Linux.
- Continue recognizing source identities stored by earlier releases as SQLite integers.
- Avoid a schema migration and avoid forcing an otherwise unnecessary one-time full reparse.
- Keep all fixtures synthetic and all outputs aggregate-first.

## Non-goals

- Changing the public JSON, CLI, MCP, or plugin contracts.
- Changing how source paths, content hashes, or parser checkpoints are calculated.
- Generalizing the source metadata schema beyond the filesystem identity failure in issue #278.

## Decision

Serialize both filesystem identifiers at the filesystem boundary as versioned text:

```text
fsid-v1:<complete decimal identifier>
```

The non-numeric prefix forces SQLite to store the values as `TEXT` even though the existing columns have `INTEGER` affinity. SQLite's dynamic typing preserves the full identifier, so the schema remains unchanged.

Both `st_dev` and `st_ino` use the same representation. This keeps the identity pair consistent and protects against either platform value exceeding SQLite's integer range.

## Compatibility

The comparison path will normalize both supported stored forms:

- a legacy SQLite integer such as `123` becomes `fsid-v1:123`;
- a current value such as `fsid-v1:123` remains `fsid-v1:123`.

This lets unchanged and append-only sources retain their existing parse checkpoints after upgrade. New or reparsed source rows persist the versioned text form.

Malformed or unsupported stored values will compare unequal rather than raising an exception. The existing planner will then choose a safe full parse, and the subsequent upsert will repair the stored identity.

## Implementation Shape

`src/codex_usage_tracker/store/sources.py` remains the single owner of this behavior:

1. Add a private filesystem-ID prefix constant and normalization helper.
2. Introduce a source metadata type that permits integer file measurements and string filesystem identifiers.
3. Serialize `stat.st_dev` and `stat.st_ino` in `_source_file_metadata`.
4. Persist the serialized values without converting them back to integers.
5. Normalize stored device and inode values in unchanged-source and append-only comparisons.

No migration is added to `store/schema.py` or `store/compression_schema.py`. The existing columns accept the versioned text values, and keeping their declarations unchanged avoids an unnecessary table rebuild.

## Error Handling

- Files that disappear or cannot be statted continue to return no metadata and are skipped as today.
- A filesystem identifier returned by `stat` is converted losslessly with Python's arbitrary-precision integer support.
- A malformed legacy database value is treated as an identity mismatch, producing a safe full parse instead of a setup failure.
- Size, modification time, checkpoint hash, and parser-state checks retain their existing behavior.

## Testing

Regression coverage will:

- simulate device and inode identifiers larger than signed 64-bit integers;
- prove the exact prefixed values persist with SQLite storage type `text`;
- prove a legacy integer identity still matches the corresponding current identity;
- prove unchanged files remain skipped and grown files remain eligible for incremental parsing;
- update existing source metadata assertions to the versioned representation.

Focused source-store tests will run first. Before the PR, the repository's lint, type-check, full test, coverage, compile, JavaScript syntax, release, build, distribution, and installed-package smoke gates will run because this changes refresh behavior and packaged source.

## Alternatives Considered

### Store prefixed text but compare raw strings

This is the smallest patch and matches the workaround attached to issue #278. It would make every legacy integer identity differ from the new prefixed form, forcing one full reparse after upgrade. Normalizing legacy rows costs little and avoids that disruption.

### Migrate the columns to declared `TEXT`

This makes the declared type more descriptive but requires a SQLite table migration for no runtime benefit. SQLite already stores the prefixed values losslessly as text in the existing columns.

### Truncate or hash identifiers into 64 bits

This would fit the existing integer representation but discards identity information and introduces collision risk into replacement detection. It is rejected.
