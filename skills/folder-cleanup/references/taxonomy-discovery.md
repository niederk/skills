# Taxonomy Discovery

PBA does not have a single codified folder taxonomy. In practice each engagement has *some* structure that drifts as work accumulates. This file describes how to **discover** what a client's working structure is and lock it in for that engagement, rather than imposing an external template.

The cleanup skill therefore treats taxonomy as a per-engagement conversation, not a global rule.

## What "discovery" looks like

Before proposing any moves on a client folder, do a structural pass:

1. **List top-level subfolders.** What's at depth 1 under the client root? Is it year-based (`2023/`, `2024/`), function-based (`Tax/`, `CAS/`, `Workpapers/`), engagement-based (`2024 Audit/`, `2024 Tax Return/`), or mixed?
2. **Sample 2–3 of the cleanest-looking subfolders.** Where does the client team naturally put things when they're being careful?
3. **Compare against 2–3 of the messiest.** What got dumped where it didn't belong? That tells you which folders are catch-alls.
4. **Look at filename conventions.** Period prefix? Suffix? Document-type tokens? Initials?

Show the user what you found and ask: "Is this the structure we want to preserve and tidy toward, or do you want to flatten/reorganize this client to match something else?"

## Useful commands during discovery

Run these against a synced client folder to summarize structure cheaply (no hashing, no plan):

```bash
# Top-level subfolders
ls -la <client-root>

# Folder names by depth, sorted by frequency
find <client-root> -type d | awk -F/ '{print NF, $0}' | sort

# Extension distribution
find <client-root> -type f | awk -F. '{print tolower($NF)}' | sort | uniq -c | sort -rn

# Files per folder (find the dumping grounds)
find <client-root> -type d -exec sh -c 'echo "$(find "$0" -maxdepth 1 -type f | wc -l) $0"' {} \; | sort -rn | head -20
```

## What to lock in once you've discovered the pattern

For each engagement the cleanup runs against, capture in the plan header:

- **Top-level shape.** "Year-based with `<YYYY>/<function>/` underneath" vs "Function-based with `<function>/<YYYY>/` underneath" vs "Flat".
- **Period encoding.** Whether the team uses `YYYY-MM`, `YYYY_MM`, `MMM YYYY`, `Q1 YYYY`, or none. Pick one and stick to it.
- **Document type conventions.** Are bank statements named `Chase 4567 Jan 2024.pdf` or `2024-01_Bank_Stmt_Chase_4567.pdf`? Match what's already working.
- **Untouchable subfolders.** Anything the deal team / external collaborators own that should be left alone.
- **Sensitive treatment.** Whether signed/efiled files live in a dedicated `Signed/` or `_Final/` folder or are mixed with workpapers.

These answers feed the `_cleanup_plan.md` header so a future run on the same client is consistent.

## When to formalize a global taxonomy

When the same patterns show up across 3+ engagements without prompting, that's a real convention worth codifying. At that point this file should be replaced with a prescriptive standard (target tree + naming rules) and the skill workflow updated to apply it. Until then, keep it conversational — the cost of imposing a template that doesn't match how the team actually works is higher than the cost of one extra discussion per client.

## What the skill does well without a fixed taxonomy

Even with no global standard, the cleanup script handles:

- **Exact duplicate detection** by SHA-256 — `IMG_4521.pdf` and `IMG_4521 (1).pdf` with identical bytes.
- **OneDrive sync conflict resolution** — `TB-DESKTOP-3KQ8MN1.xlsx` archived against the canonical sibling.
- **Sensitive-file protection** — signed/efiled/IRS-notice files default to skip regardless of structure.
- **Lock and temp file skipping** — `~$*`, `*.tmp`, `Thumbs.db`.
- **Cloud-only file flagging** — surface without forcing hydrate.
- **Default-name surfacing** — `Untitled.xlsx`, `IMG_*.pdf` go to `needs-human` for renaming.

What it does **not** do without a taxonomy:

- Propose target subfolders for files. Any file that isn't a duplicate, conflict, or sensitive lands in `needs-human` so you and the client can decide where it belongs.
- Auto-rename to a canonical filename convention. Renames are proposed only when there's a clear pattern in the existing folder.

This is by design. Until the taxonomy is real, the skill should find and stage problems for human decisions, not invent structure.
