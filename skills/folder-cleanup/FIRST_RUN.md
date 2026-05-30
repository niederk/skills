# First-Run Checklist

Use this the first time you run `folder-cleanup` against a real client folder. Stop at the `analyze` step — do **not** execute on real client data until the plan has been reviewed and the rules tuned to your reality.

## Pre-flight

Before invoking the skill:

- [ ] OneDrive client shows **"Up to date"** for the folder you're cleaning. Not "Syncing", not "Paused". Running mid-sync causes conflict files.
- [ ] No one on the team is actively editing files in this engagement folder right now. If you see `~$*.docx` or `~$*.xlsx` files, someone has them open — wait or coordinate.
- [ ] You know how to roll back via OneDrive version history if needed (right-click → Version History on SharePoint). 30 days is the typical retention.
- [ ] Python 3 is installed and on `PATH`. Quick check: `python3 --version` or `python --version`.

## Verify the skill is installed

In Claude Code, type `/skills`. You should see `folder-cleanup` in the list. If not, re-run the install command — the skill folder must live at `~/.claude/skills/folder-cleanup/` (Mac/Linux) or `%USERPROFILE%\.claude\skills\folder-cleanup\` (Windows).

## First run: analyze only

Open Claude Code in any project (or just any folder — the skill doesn't care about the working directory). Tell it:

> Use folder-cleanup to **analyze only** (do not dry-run or execute) the folder at `<absolute-path-to-client>`. Stop after producing the plan and walk me through it.

Claude should:

1. Ask the Phase 0 onboarding questions (sync status, taxonomy discovery, scope guards).
2. Run `cleanup.py analyze` against the folder.
3. Write `_cleanup_plan.md` and `_cleanup_plan.json` as siblings to the client root.
4. Read back a summary — counts per action category and any surprises.

## What to look for in the plan

- **Counts.** Are the numbers in the right ballpark for what you'd expect?
- **`skip` items.** These are sensitive files (signed/efiled/IRS/legal). Confirm the right things landed here.
- **`archive-duplicate` items.** Spot-check 3–5. The winner (the file *not* listed as a duplicate) should be the version you'd actually keep.
- **`archive-conflict` items.** OneDrive sync conflicts (`-DESKTOP-*`, `-Conflict-*`). Confirm they really are conflicts.
- **`needs-human` items.** This is where the conversation happens. Everything not handled deterministically goes here. **Expect this to be most of the files** since there's no taxonomy yet.

## Red flags — stop and tell Claude

- A signed tax return, e-filed form, or IRS notice ended up in `archive-duplicate` or `move` instead of `skip`. **Do not proceed.** Tell Claude and we tune the sensitive-trigger patterns.
- The plan proposes archiving a file you know is the only copy of something important.
- Counts look way off (e.g. you have ~500 files but only 200 appear in the plan — something was skipped that shouldn't have been).
- Paths in the plan contain unexpected characters or look truncated.

## After you've reviewed

If the plan looks reasonable but needs tuning:

> Here's the `_cleanup_plan.md` Claude produced. Items #X, #Y, #Z look wrong because [reason]. Can we adjust the rules and re-analyze?

We'll edit `references/classification-rules.md`, push the update, you'll re-pull, re-run analyze, re-review.

If the plan looks **right**:

1. Dry-run: `cleanup.py dry-run --plan-json ... --report ...`
2. Review the dry-run report for collisions or path-length issues.
3. Execute: `cleanup.py execute --plan-json ... --log ...`
4. Verify: spot-check 3–5 files moved correctly, confirm `_Archive/` has what you expected.
5. Keep `_cleanup_log.json` until you're sure you don't want to undo.

## If something goes wrong after execute

```bash
python ~/.claude/skills/folder-cleanup/scripts/cleanup.py undo --log "<root>/_cleanup_log.json"
```

Reverses every move. The log is consumed after undo so you can't accidentally undo twice.

## After a successful run

Make a note (in your own notes or in `~/.claude/CLAUDE.md`) of:

- Which client you ran it on, when, and how many files were affected.
- Any rule tweaks that came out of the run, so they apply to the next client too.
- Any patterns specific to that client (e.g. "Commure puts signed K-1s in `/Tax Returns/Issued/`, not `/Signed/`") so future runs preserve them.

After 3–4 client runs, the patterns start to converge and you can codify a real PBA taxonomy — at which point `references/taxonomy-discovery.md` gets replaced with a prescriptive standard.
