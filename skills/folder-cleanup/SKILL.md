---
name: folder-cleanup
description: Clean up messy client engagement folders on OneDrive/SharePoint by classifying files, detecting duplicates and sync conflicts, and reorganizing into a target taxonomy. Use this skill whenever the user asks to clean up, organize, tidy, deduplicate, or reorganize a client folder, engagement folder, working papers folder, or anything resembling "Clients and Prospects/<Client>" trees, even if they don't explicitly say "skill". Strongly prefer non-destructive plan + dry-run + execute phases with a reversible undo log; never delete, only archive.
---

# Folder Cleanup

A skill for cleaning up disorganized client engagement folders (CAS, tax, M&A, FP&A) without losing work. The flow is deliberate: **plan → review → dry-run → execute → verify**, with archiving instead of deletion and a JSON undo log for every executed run.

## Core principles

1. **Archive, never delete.** Every file the plan removes goes under `_Archive/<run-id>/<original-relative-path>/`. Empty folders get tombstoned with a `.archived.txt` breadcrumb.
2. **Plan-heavy.** The plan is a markdown report a human can red-line. Don't move anything until the user has reviewed it. Then dry-run. Then execute.
3. **OneDrive/SharePoint safety first.** Skip lock files (`~$*.docx`), skip cloud-only files unless the user opts in, never produce paths that violate SharePoint limits, never traverse a folder being co-authored if the lock pattern is present.
4. **Deterministic where possible, conversational where useful.** Walking, hashing, and moving are scripted. Taxonomy decisions are conversational because PBA's standard drifts in practice and each engagement has quirks.
5. **Client data isolation.** Treat one client's folder as a sealed unit. Do not carry naming conventions or quirks from one client to another unless the user says so.

## When this skill triggers

Phrases like:
- "Clean up the Commure folder."
- "This client's folder is a mess, can you organize it?"
- "Dedupe and reorganize `Clients and Prospects/<Name>`."
- "Sort 2024 working papers into our standard structure."
- "There's a bunch of `(1)` and `_FINAL_v2` files in the engagement folder."

## The workflow

### Phase 0: Onboard the cleanup

Before touching anything, gather:

1. **Target root.** Absolute path to the folder to clean. Confirm it's a single client/engagement, not the whole `Clients and Prospects` tree.
2. **Sync status.** Is this OneDrive/SharePoint synced locally, or are they pointing me at a network drive? If OneDrive, check `attrib` (Windows) or extended attrs for cloud-only files. Don't force-hydrate large cloud-only files just to hash them — flag and ask.
3. **Taxonomy discovery.** PBA has no codified taxonomy yet — each engagement has its own working structure. Before proposing any moves, do a structural pass and show the user what you found. Read `references/taxonomy-discovery.md` for the workflow. Ask: "Is this the structure we tidy toward, or do you want to reorganize this client to something else?" Capture the answer in the plan header.
4. **Scope guards.** Confirm:
   - Year boundary (clean only 2024, or all years?)
   - Anything off-limits (signed engagement letters, e-filed returns, originals, deal-team subfolders, external-collab folders)
   - Whether to consider `_Archive/` from a previous run as a source (default: ignore)

If any of these are unclear, ask once with a concrete proposed default rather than peppering the user.

### Phase 1: Analyze

Run the analyzer to walk the tree, classify files, detect duplicates and sync conflicts, and emit a plan.

```bash
python <skill-dir>/scripts/cleanup.py analyze \
    --root "<absolute-path-to-client-folder>" \
    --plan-out "<root>/_cleanup_plan.md" \
    --plan-json "<root>/_cleanup_plan.json"
```

The analyzer writes two siblings into the root:

- `_cleanup_plan.md` — human-reviewable plan, grouped by action (rename / move / archive-duplicate / archive-stale / skip-with-reason). Each entry includes source path, proposed destination, and the rule that triggered the action.
- `_cleanup_plan.json` — machine-readable plan the dry-run and execute phases consume.

Read the markdown plan back to the user as a summary (counts per action category, top 10 most surprising items, anything skipped that they should know about). Don't read the full file unless asked; it can be thousands of lines.

**Walk through anything the analyzer marked `needs-human` with the user before proceeding.** That's the bucket where rules couldn't decide. Examples: a PDF named `Engagement_Letter_2023.pdf` that lives under a `2024/` folder; a workbook with a name that suggests both source and deliverable; a folder containing a single `Untitled.xlsx` of unknown origin.

### Phase 2: Edit the plan if needed

The user may want to override decisions. The plan JSON is editable — keys are stable, each action has an `id`. Tell the user: "If you want to change anything, edit `_cleanup_plan.json` directly (the markdown is just for reading), or tell me the IDs to change and I'll patch it."

Patch a small number of items by reading the JSON, editing, and writing it back. For larger changes, re-run analyze with adjusted flags rather than hand-editing en masse.

### Phase 3: Dry-run

```bash
python <skill-dir>/scripts/cleanup.py dry-run \
    --plan-json "<root>/_cleanup_plan.json" \
    --report "<root>/_cleanup_dryrun.md"
```

This simulates every move/rename/archive without touching the filesystem and writes a report showing:
- Final tree as it would look after execution
- Any collisions (two files headed for the same destination) — these block execution
- Any path-length or illegal-character violations
- Any files that have changed since analysis (size or mtime drift)

If the report is clean, present it to the user and confirm before execute. If there are collisions or drifts, fix in the plan and re-dry-run.

### Phase 4: Execute

```bash
python <skill-dir>/scripts/cleanup.py execute \
    --plan-json "<root>/_cleanup_plan.json" \
    --log "<root>/_cleanup_log.json"
```

The executor:
- Refuses to run if the plan has unresolved collisions or path violations.
- Performs moves in dependency order (archive duplicates first so their slots free up for renames).
- Writes `_cleanup_log.json` mapping every `(original_path → new_path)`, plus a SHA-256 captured at move time.
- Stops on first error and reports — does not roll back automatically. Use `undo` to reverse.

After execute, the root contains:
- The reorganized tree
- `_Archive/<run-id>/...` mirroring the original relative paths of archived files
- `_cleanup_log.json` (do not delete — needed for undo)

### Phase 5: Verify

After execute, run a quick sanity pass:
- Spot-check 3–5 representative files: open them or at least confirm they exist and hash-match.
- Confirm no `~$*` lock files were moved (means a file was open during execute — flag).
- Confirm `_Archive/` count + final tree count == pre-clean count.

Tell the user: counts before/after, any anomalies, and where the undo log lives.

### Undo

If the user is unhappy with results:

```bash
python <skill-dir>/scripts/cleanup.py undo --log "<root>/_cleanup_log.json"
```

Reverses every move recorded in the log. Files in `_Archive/` go back to their original locations. The log is consumed (renamed to `_cleanup_log.<timestamp>.undone.json`) so you can't accidentally undo twice.

## Key references

Load these on demand, not all upfront:

- `references/taxonomy-discovery.md` — How to discover an engagement's working structure during Phase 0, since PBA has no global taxonomy. Read before proposing any reorganization.
- `references/classification-rules.md` — Patterns for detecting duplicates, sync conflicts, periods, and document categories. Read when the user asks why something was classified a certain way, or when adding new rules.
- `references/onedrive-sharepoint-gotchas.md` — Path length limits, illegal characters, lock files, cloud-only files, sync conflict patterns. Read before any execute against a OneDrive/SharePoint path.

## What this skill is not

- Not a backup tool. The user is responsible for OneDrive version history / their own backups before a large run.
- Not a content classifier — it does not open Excel or PDF files to read their contents. Classification is filename + extension + path-based. If filename-based classification can't decide, the file goes to `needs-human` for the user to call.
- Not for cross-client work. Run it once per client folder.
- **Not a tree-imposer.** Without a codified PBA taxonomy, the script does not propose target subfolders for unclassified files. Duplicates, sync conflicts, and sensitive files are handled deterministically; everything else is surfaced as `needs-human` so you and the client decide structure together.

## Sensitive matters

If the cleanup touches signed tax returns, e-filed forms, signed engagement letters, or anything that looks like litigation/audit-related material, flag it before executing and recommend the user verify retention rules first. These items default to `skip` in the rules — do not override without explicit user authorization.
