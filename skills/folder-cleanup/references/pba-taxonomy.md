# PBA Engagement Folder Taxonomy

This file is the **target structure** the cleanup skill organizes toward. The standard drifts in practice, so this file is meant to be reviewed and adjusted per engagement before a run.

## Default target tree

```
<Client>/
├── 01_Engagement/
│   ├── Engagement_Letters/
│   ├── Scope_Changes/
│   └── Communication/
├── 02_Source_Documents/
│   └── <YYYY>/
│       ├── Bank_Statements/
│       ├── Credit_Card_Statements/
│       ├── Vendor_Invoices/
│       ├── Payroll/
│       └── Other/
├── 03_Workpapers/
│   └── <YYYY>/
│       ├── Trial_Balance/
│       ├── General_Ledger/
│       ├── Reconciliations/
│       └── Lead_Sheets/
├── 04_Deliverables/
│   └── <YYYY>/
│       ├── Financial_Statements/
│       ├── Tax_Returns/
│       ├── Models/
│       └── Decks/
├── 05_Tax/
│   └── <YYYY>/
│       ├── Returns/
│       ├── Extensions/
│       ├── K-1s/
│       └── Notices/
├── 06_MA/                    # only present for M&A engagements
│   ├── Diligence/
│   ├── QofE/
│   └── Deal_Docs/
├── 99_Internal/
│   ├── Planning/
│   ├── Budget_and_Time/
│   └── Notes/
└── _Archive/                 # populated by cleanup runs
    └── <run-id>/
```

## Conventions

**Period encoding in filenames:** `YYYY-MM` for monthly, `YYYY-Qn` for quarterly, `YYYY` for annual. Period goes at the start of the filename when the document is period-specific:
- `2024-Q1_Bank_Stmt_Chase_4567.pdf`
- `2024_Form_1120_Final.pdf`
- `2024-03_TB_Adjusted.xlsx`

**Versioning:** No `_v2`, `_FINAL`, `_FINAL_FINAL`. Final goes in the canonical location; prior versions go in `_Archive/<run-id>/` if the cleanup found them, or in OneDrive version history if the user is relying on that.

**Account masking:** If filenames contain full account numbers, the cleanup flags them but does not auto-rename. The user decides whether to mask (e.g. `Chase_xxx4567`) before approving the plan.

## Per-engagement deviations

When you run the cleanup on a specific client, ask the user:

1. Does this client need an `06_MA/` branch?
2. Are tax workpapers kept separately under `05_Tax/Workpapers/` or merged into `03_Workpapers/`? (PBA practice varies.)
3. Is there a deal-team or external-collab subfolder that should be left untouched?
4. Should prior years be collapsed into a single `Archive_<Year>/` rather than promoted into the main tree?

Capture the answers in the plan's header so the next run on the same client is consistent.

## Edit this file

This template is a starting point. Once the real PBA standard stabilizes, replace the sections above with the canonical version and remove this note. Keep the "Conventions" section even if structure changes — period encoding and versioning rules carry across engagements.
