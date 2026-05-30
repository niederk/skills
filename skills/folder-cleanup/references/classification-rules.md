# Classification Rules

These are the patterns the analyzer uses to decide what to do with each file. Rules are filename + path-based — the analyzer does not read file contents.

## Skip (do not touch)

| Pattern | Reason |
|---|---|
| `~$*` | Office lock file — file is open elsewhere |
| `*.tmp`, `*.~tmp` | Temp file from Office / sync |
| `Thumbs.db`, `.DS_Store`, `desktop.ini` | OS metadata |
| `*.lnk` | Windows shortcut — leave alone |
| `_Archive/**` | Prior cleanup runs |
| Files marked cloud-only by OneDrive | Don't force hydrate; flag for user |

## Sync-conflict patterns (archive after dedup check)

OneDrive and SharePoint append device or user identifiers when sync conflicts:

- `<name>-<DEVICE-NAME>.<ext>` where `<DEVICE-NAME>` is uppercase with letters and digits, e.g. `TB-DESKTOP-3KQ8MN1.xlsx`
- `<name> (<user>'s conflicted copy <YYYY-MM-DD>).<ext>`
- `<name>-Conflict-<digits>.<ext>`

If the canonical file (same name without the suffix) exists and hashes match: archive the conflict.
If hashes differ: surface to `needs-human` — the user has to pick the winner.

## Duplicate suffix patterns (archive losers)

- ` (1)`, ` (2)`, ... ` (N)` immediately before the extension
- ` - Copy`, ` - Copy (N)`
- `_copy`, `_copy_N`
- Same stem + `_FINAL`, `_FINAL_v2`, `_FINAL_FINAL`, `_v2`, `_v3`, etc.

Resolution:
1. If hashes are identical across the group, keep the shortest/cleanest name and archive the rest.
2. If hashes differ, keep the most recently modified and archive others with a note. User reviews in plan.

## Default-name patterns (rename after classification)

Files with default scanner / camera / app names need the user's input on intent. They go to `needs-human` unless the path strongly implies a category:

- `IMG_*.jpg`, `IMG_*.jpeg`, `IMG_*.heic`
- `Scan*.pdf`, `Scanned Document*.pdf`, `Document*.pdf`
- `Untitled*.xlsx`, `Untitled*.docx`
- `New Microsoft *.xlsx`, `New Microsoft *.docx`
- `image.png`, `screenshot*.png`

If the parent folder name encodes a clear category (e.g. `2024 Bank Statements/IMG_4521.pdf`), the analyzer proposes `2024-MM_Bank_Stmt_<institution>_<last4>.pdf` with `MM` and the institution/last4 as `<TBD>` placeholders for the user to fill.

## Period detection

Searched in this order on filename, then on parent folder names up to root:

1. `YYYY-MM-DD` (e.g. `2024-03-31`)
2. `YYYY-MM` / `YYYY_MM` / `YYYYMM`
3. `YYYY-Qn` / `Qn YYYY` / `Qn-YYYY`
4. `MMM YYYY` / `MMMM YYYY` (e.g. `Mar 2024`, `March 2024`)
5. `YYYY` alone (annual)

If multiple periods are found, the most specific wins. If filename and folder disagree, the analyzer flags `period-conflict`.

## Document category heuristics

Filename or path matches (case-insensitive) trigger category:

| Category | Triggers |
|---|---|
| Engagement Letter | `engagement letter`, `^EL_`, `engagement_ltr`, `signed eng` |
| Bank Statement | `bank stmt`, `bank statement`, `chase`, `bofa`, `wells`, `silicon valley`, `mercury` (combined with statement keywords or in a `Bank Statements` folder) |
| Credit Card Statement | `cc stmt`, `credit card`, `amex`, `visa stmt`, `mastercard stmt` |
| Trial Balance | `\bTB\b`, `trial balance`, `trial_bal` |
| General Ledger | `\bGL\b`, `general ledger`, `gl_export`, `gl detail` |
| Tax Return — 1120 | `1120`, `corporate return` |
| Tax Return — 1065 | `1065`, `partnership return` |
| Tax Return — 1040 | `1040`, `individual return` |
| K-1 | `K-1`, `K1`, `schedule k-1` |
| Form 1099 | `1099`, `1099-misc`, `1099-nec` |
| Reconciliation | `recon`, `reconciliation`, `tie out` |
| Financial Statements | `\bFS\b`, `financial statements`, `income statement`, `balance sheet`, `cash flow` |
| QofE | `qofe`, `quality of earnings`, `due diligence`, `\bDD\b` |
| Engagement Plan / Budget | `budget`, `planning memo`, `time budget` |

Standalone bare words (`TB`, `GL`, `FS`, `EL`, `DD`) only match when they are word-bounded — not as substrings.

## Sensitive — never auto-move without explicit user approval

These categories default to `skip-sensitive` in the plan even when confidently classified:

- Anything matching `signed`, `executed`, `e-filed`, `efiled`
- IRS notices: `IRS notice`, `CP\d+`, `LT\d+`
- State tax notices: `notice`, `assessment`, `audit`
- Any PDF in a folder named `Litigation`, `Audit`, `Legal`, `Disputes`

The plan surfaces these for the user to acknowledge. The user can flip them to `move` per item if appropriate, but the rule is opt-in not opt-out.

## "needs-human" bucket

A file lands here when:
- Default name + parent folder doesn't disambiguate
- Period conflict between filename and path
- Hash differs across a duplicate group
- Filename suggests two categories
- Path length after proposed rename would exceed 380 chars (SharePoint cushion)
- Filename contains characters illegal in SharePoint and the analyzer can't auto-strip safely

The plan presents these one per line with the reason and a suggested action the user can accept or override.
