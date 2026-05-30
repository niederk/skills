# OneDrive & SharePoint Gotchas

Read this before any execute against a OneDrive or SharePoint-synced path. Most of these can corrupt sync state or silently fail.

## Path length limits

| System | Limit | Cushion the skill enforces |
|---|---|---|
| Windows local path (no long-path prefix) | 260 chars | n/a |
| Windows with long-path prefix | 32,767 chars | n/a |
| OneDrive / SharePoint full URL path | 400 chars | **380 chars** |
| Individual file or folder name | 255 chars | **240 chars** |

When proposing a destination path, the analyzer rejects anything over 380 chars and routes the file to `needs-human`. The user can shorten the engagement folder name or move part of the tree closer to root.

## Illegal characters

SharePoint and OneDrive disallow these in file or folder names:

```
~ # % & * { } \ : < > ? / + | "
```

Plus:
- Leading or trailing spaces
- Leading or trailing periods
- Names ending in `.lock`
- Reserved names: `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9` (case-insensitive, with or without extension)

The analyzer auto-strips illegal chars when proposing a clean filename **only** if the strip is unambiguous (e.g. dropping a trailing space). Anything else goes to `needs-human`.

## Lock files and open files

- `~$<filename>.docx` / `~$<filename>.xlsx` — Office is editing the file. Skip both the lock and the locked file. If a lock file exists with no canonical sibling, leave it; the user should investigate.
- `<filename>.tmp`, `<filename>.~tmp` — sync or save in progress. Skip.
- Files locked by another process: a move will fail. The executor catches this, logs, and continues. The user retries after closing the file.

## Cloud-only (Files On-Demand) files

OneDrive can mark files as "online-only" — the file appears in the directory listing with size, but contents are in the cloud until accessed. Hashing forces a download.

The analyzer detects cloud-only files via:
- Windows: `attrib` flags (`P` = pinned, `O` = online-only, `U` = unpinned). Files with `O` and not `P` are cloud-only.
- macOS: extended attribute `com.apple.icloud.fileprovider.materialization-state`.

Default behavior: **flag, do not hydrate**. The plan lists cloud-only files with their sizes and asks the user whether to:
1. Skip them entirely (leave in place, no dedup analysis)
2. Hydrate the small ones (under a threshold, e.g. 5 MB) for hashing
3. Hydrate everything (slow, expensive on metered connections)

Forcing a hydrate of hundreds of large files is disruptive — never do it without explicit confirmation.

## Sync conflict patterns

The cleanup treats these as conflicts to resolve, not legitimate files:

- `<name>-<DEVICENAME>.<ext>` — OneDrive sync conflict from a specific machine. Device name pattern: 1+ uppercase/digit char block(s) separated by hyphens, e.g. `-DESKTOP-3KQ8MN1`, `-LAPTOP-A2B3C4D`.
- `<name> (<user>'s conflicted copy <YYYY-MM-DD>).<ext>` — older OneDrive personal pattern.
- `<name>-Conflict-<digits>.<ext>` — SharePoint co-authoring conflict.

If the canonical sibling (same stem without the conflict suffix) exists and hashes match, the conflict is archived. If hashes differ, it goes to `needs-human` — the user must pick a winner.

## Co-authoring in progress

If multiple `~$*` lock files exist in a subfolder simultaneously, someone may be co-authoring across several files. The analyzer flags the subfolder and recommends the user notify the team or wait until edits are checked in. Don't run execute against an actively co-authored subtree.

## Move semantics on synced volumes

- A move within the same OneDrive root is fast and preserves version history.
- A move out of OneDrive (e.g. to a local-only drive) **breaks** version history. The skill never proposes cross-volume moves; if the archive root is on a different volume, the user is warned and asked to confirm.
- A rename within the same folder also preserves version history. Renames are safe.

## Permissions and shared folders

A subfolder may be a SharePoint shared folder mounted into another user's OneDrive. Moves there can change effective permissions. The analyzer detects this on Windows by checking for the `O` reparse point attribute or the SharePoint shortcut `.url`/`.lnk` markers; on macOS by the `~/Library/CloudStorage/SharePoint-*` mount path. Flagged as `shared-mount` in the plan and routed to `needs-human`.

## Recommended pre-flight

Before execute, confirm with the user:

1. The OneDrive client is running and showing "Up to date" (not "Syncing" or "Paused"). Running cleanup mid-sync causes conflicts.
2. No team members are actively editing files in this engagement folder right now.
3. Recent OneDrive version history is recent enough to recover from a mistake (default 30 days for SharePoint, 30+ days for personal — confirm).

These are user actions, not script actions. The skill prompts but does not check programmatically.
