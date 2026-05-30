#!/usr/bin/env python3
"""Folder cleanup orchestrator: analyze, dry-run, execute, undo.

Run a phase against a client folder. The skill conductor (SKILL.md) walks the
user through plan -> review -> dry-run -> execute -> verify. Each phase is
deterministic and re-runnable; execute writes an undo log so any run can be
reversed.

Stdlib only by design — this script runs on whatever Python the user has on
their workstation or in a Cowork environment, without pip installs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

# --- Constants -----------------------------------------------------------

SHAREPOINT_PATH_LIMIT = 380          # 400 hard, 20-char cushion
SHAREPOINT_NAME_LIMIT = 240          # 255 hard, 15-char cushion
ILLEGAL_NAME_CHARS = set('~#%&*{}\\:<>?/+|"')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
HASH_BLOCK = 1 << 20                 # 1 MiB
HASH_SIZE_CAP_BYTES = 500 * 1024 * 1024   # don't hash above 500 MB unless told

SKIP_NAME_PATTERNS = [
    re.compile(r"^~\$"),                 # Office lock
    re.compile(r"^\.~lock\."),           # LibreOffice lock
    re.compile(r"\.tmp$", re.IGNORECASE),
    re.compile(r"\.~tmp$", re.IGNORECASE),
    re.compile(r"^Thumbs\.db$", re.IGNORECASE),
    re.compile(r"^\.DS_Store$"),
    re.compile(r"^desktop\.ini$", re.IGNORECASE),
]

SKIP_DIR_NAMES = {"_Archive", ".git", "$RECYCLE.BIN", "System Volume Information"}

DUPLICATE_SUFFIX_PATTERNS = [
    re.compile(r"^(?P<stem>.+?)\s*\((?P<n>\d+)\)$"),                     # "name (1)"
    re.compile(r"^(?P<stem>.+?)\s*-\s*Copy(?:\s*\((?P<n>\d+)\))?$"),     # "name - Copy"
    re.compile(r"^(?P<stem>.+?)[_\s]copy(?:[_\s]\d+)?$", re.IGNORECASE), # "name_copy_2"
    re.compile(r"^(?P<stem>.+?)[_\s](?:FINAL(?:[_\s]FINAL)?|final)$"),
    re.compile(r"^(?P<stem>.+?)[_\s]v\d+$", re.IGNORECASE),              # "_v2", "_v10"
]

SYNC_CONFLICT_PATTERNS = [
    re.compile(r"^(?P<stem>.+?)-(?:[A-Z0-9]+)(?:-[A-Z0-9]+)+$"),         # "-DESKTOP-3KQ8MN1"
    re.compile(r"^(?P<stem>.+?)\s+\(.+?'s\s+conflicted\s+copy\s+\d{4}-\d{2}-\d{2}\)$"),
    re.compile(r"^(?P<stem>.+?)-Conflict-\d+$"),
]

DEFAULT_NAME_PATTERNS = [
    re.compile(r"^IMG[_-]?\d+$", re.IGNORECASE),
    re.compile(r"^Scan(ned)?(\s*Document)?\s*\d*$", re.IGNORECASE),
    re.compile(r"^Document\s*\d*$", re.IGNORECASE),
    re.compile(r"^Untitled\s*\d*$", re.IGNORECASE),
    re.compile(r"^New Microsoft.*", re.IGNORECASE),
    re.compile(r"^image$", re.IGNORECASE),
    re.compile(r"^screenshot.*", re.IGNORECASE),
]

PERIOD_PATTERNS = [
    (re.compile(r"\b(20\d{2})[-_/.](\d{2})[-_/.](\d{2})\b"), "ymd"),
    (re.compile(r"\b(20\d{2})[-_/](\d{2})\b"), "ym"),
    (re.compile(r"\b(20\d{2})(\d{2})\b"), "ym_compact"),
    (re.compile(r"\b(20\d{2})[-_\s]?Q([1-4])\b", re.IGNORECASE), "yq"),
    (re.compile(r"\bQ([1-4])[-_\s]?(20\d{2})\b", re.IGNORECASE), "qy"),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b", re.IGNORECASE), "moy"),
    (re.compile(r"\b(20\d{2})\b"), "y"),
]

MONTH_TO_NUM = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
)}

CATEGORY_RULES = [
    ("engagement_letter", [r"engagement\s*letter", r"\bEL_", r"engagement[_\s]ltr", r"signed\s+eng"]),
    ("bank_statement", [r"bank\s*st(a|m)t", r"bank\s+statement"]),
    ("credit_card_statement", [r"cc\s*st(a|m)t", r"credit\s*card\s*stmt", r"amex\s*stmt", r"visa\s*stmt"]),
    ("trial_balance", [r"\bTB\b", r"trial\s*balance", r"trial[_\s]bal"]),
    ("general_ledger", [r"\bGL\b", r"general\s*ledger", r"gl[_\s]export", r"gl\s*detail"]),
    ("tax_1120", [r"\b1120\b", r"corporate\s+return"]),
    ("tax_1065", [r"\b1065\b", r"partnership\s+return"]),
    ("tax_1040", [r"\b1040\b", r"individual\s+return"]),
    ("k1", [r"\bK-?1\b", r"schedule\s*k-?1"]),
    ("form_1099", [r"\b1099(-\w+)?\b"]),
    ("reconciliation", [r"\brecon\b", r"reconciliation", r"tie[\s_]?out"]),
    ("financial_statements", [r"\bFS\b", r"financial\s+statements?", r"income\s+statement", r"balance\s+sheet", r"cash\s*flow"]),
    ("qofe", [r"\bqofe\b", r"quality\s+of\s+earnings", r"due\s+diligence", r"\bDD\b"]),
    ("budget", [r"\bbudget\b", r"planning\s+memo", r"time\s+budget"]),
]
CATEGORY_RULES = [(cat, [re.compile(p, re.IGNORECASE) for p in pats]) for cat, pats in CATEGORY_RULES]

SENSITIVE_TRIGGERS = [
    re.compile(r"\bsigned\b", re.IGNORECASE),
    re.compile(r"\bexecuted\b", re.IGNORECASE),
    re.compile(r"\be-?filed\b", re.IGNORECASE),
    re.compile(r"IRS\s*notice", re.IGNORECASE),
    re.compile(r"\bCP\d+\b"),
    re.compile(r"\bLT\d+\b"),
]
SENSITIVE_PARENT_DIRS = {"Litigation", "Audit", "Legal", "Disputes"}


# --- Data classes --------------------------------------------------------

@dataclass
class FileRecord:
    abs_path: str
    rel_path: str
    name: str
    stem: str
    ext: str
    size: int
    mtime: float
    sha256: str | None = None
    is_cloud_only: bool = False
    is_sensitive: bool = False
    period: str | None = None
    period_source: str | None = None
    category: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Action:
    id: int
    kind: str             # rename | move | archive-duplicate | archive-conflict | skip | needs-human
    src: str              # absolute path
    dst: str | None       # absolute path or None for skip/needs-human
    reason: str
    rule: str
    sha256: str | None = None
    size: int | None = None


# --- Phase 1: analyze ----------------------------------------------------

def is_cloud_only(path: Path) -> bool:
    """Best-effort detection of OneDrive Files-On-Demand cloud-only files.

    Returns True only when we can affirmatively detect cloud-only state.
    Default False means hashing will proceed, which is correct for fully
    materialized files.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
            FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
            if attrs == -1:
                return False
            return bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN))
        except Exception:
            return False
    return False


def should_skip_name(name: str) -> bool:
    return any(p.search(name) for p in SKIP_NAME_PATTERNS)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(HASH_BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def detect_period(name_no_ext: str, parent_parts: list[str]) -> tuple[str, str] | tuple[None, None]:
    candidates = [name_no_ext] + list(reversed(parent_parts))
    for source_idx, text in enumerate(candidates):
        for regex, kind in PERIOD_PATTERNS:
            m = regex.search(text)
            if not m:
                continue
            src_label = "filename" if source_idx == 0 else f"path[{source_idx-1}]"
            if kind == "ymd":
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", src_label
            if kind in ("ym", "ym_compact"):
                return f"{m.group(1)}-{m.group(2)}", src_label
            if kind == "yq":
                return f"{m.group(1)}-Q{m.group(2)}", src_label
            if kind == "qy":
                return f"{m.group(2)}-Q{m.group(1)}", src_label
            if kind == "moy":
                mm = MONTH_TO_NUM[m.group(1).lower()[:3]]
                return f"{m.group(2)}-{mm:02d}", src_label
            if kind == "y":
                return m.group(1), src_label
    return None, None


def classify_category(name: str, parent_parts: list[str]) -> str | None:
    haystack = name + " " + " ".join(parent_parts)
    for cat, regexes in CATEGORY_RULES:
        if any(r.search(haystack) for r in regexes):
            return cat
    return None


def is_sensitive(name: str, parent_parts: list[str]) -> bool:
    if any(d in parent_parts for d in SENSITIVE_PARENT_DIRS):
        return True
    return any(t.search(name) for t in SENSITIVE_TRIGGERS)


def has_default_name(stem: str) -> bool:
    return any(p.match(stem) for p in DEFAULT_NAME_PATTERNS)


def duplicate_suffix_match(stem: str) -> str | None:
    """Return the canonical stem if `stem` looks like a duplicate suffix variant."""
    for p in DUPLICATE_SUFFIX_PATTERNS:
        m = p.match(stem)
        if m:
            return m.group("stem").strip()
    return None


def sync_conflict_match(stem: str) -> str | None:
    for p in SYNC_CONFLICT_PATTERNS:
        m = p.match(stem)
        if m:
            return m.group("stem").strip()
    return None


def validate_dest_path(root: Path, dest_rel: str) -> str | None:
    """Return error message if proposed relative path is invalid, else None."""
    full = root / dest_rel
    if len(str(full)) > SHAREPOINT_PATH_LIMIT:
        return f"path-too-long ({len(str(full))} > {SHAREPOINT_PATH_LIMIT})"
    for part in Path(dest_rel).parts:
        if len(part) > SHAREPOINT_NAME_LIMIT:
            return f"name-too-long ({part[:30]}... > {SHAREPOINT_NAME_LIMIT})"
        bad = set(part) & ILLEGAL_NAME_CHARS
        if bad:
            return f"illegal-chars ({''.join(sorted(bad))})"
        if part.endswith(" ") or part.endswith("."):
            return "trailing-space-or-dot"
        if part.startswith(" "):
            return "leading-space"
        base = part.rsplit(".", 1)[0].upper() if "." in part else part.upper()
        if base in RESERVED_NAMES:
            return f"reserved-name ({base})"
    return None


def walk_tree(root: Path, hash_cap: int) -> list[FileRecord]:
    records: list[FileRecord] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in filenames:
            if should_skip_name(name):
                continue
            abs_path = Path(dirpath) / name
            try:
                st = abs_path.stat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            stem, _, ext = name.rpartition(".")
            if not stem:
                stem, ext = name, ""
            rel = abs_path.relative_to(root)
            parent_parts = list(rel.parent.parts)
            cloud_only = is_cloud_only(abs_path)
            rec = FileRecord(
                abs_path=str(abs_path),
                rel_path=str(rel),
                name=name,
                stem=stem,
                ext=ext.lower(),
                size=st.st_size,
                mtime=st.st_mtime,
                is_cloud_only=cloud_only,
                period=None,
                period_source=None,
            )
            period, period_src = detect_period(stem, parent_parts)
            rec.period = period
            rec.period_source = period_src
            rec.category = classify_category(name, parent_parts)
            rec.is_sensitive = is_sensitive(name, parent_parts)
            if cloud_only:
                rec.notes.append("cloud-only: not hashed")
            elif st.st_size > hash_cap:
                rec.notes.append(f"size>{hash_cap}: not hashed")
            else:
                try:
                    rec.sha256 = sha256_file(abs_path)
                except (OSError, PermissionError) as e:
                    rec.notes.append(f"hash-failed: {e.__class__.__name__}")
            records.append(rec)
    return records


def propose_actions(root: Path, records: list[FileRecord]) -> list[Action]:
    """Convert the file inventory into a list of Actions."""
    actions: list[Action] = []
    next_id = [0]

    def add(kind: str, src: str, dst: str | None, reason: str, rule: str,
            sha256: str | None = None, size: int | None = None) -> None:
        actions.append(Action(
            id=next_id[0], kind=kind, src=src, dst=dst,
            reason=reason, rule=rule, sha256=sha256, size=size,
        ))
        next_id[0] += 1

    sensitive_handled: set[str] = set()
    # 0) Sensitive files surface first so duplicate logic cannot auto-archive them.
    for r in records:
        if r.is_sensitive:
            sensitive_handled.add(r.abs_path)
            add(
                kind="skip",
                src=r.abs_path,
                dst=None,
                reason="sensitive (signed/efiled/notice/legal) — explicit approval required",
                rule="sensitive-default-skip",
                sha256=r.sha256, size=r.size,
            )

    # 1) Group by hash to detect exact duplicates (excluding sensitive)
    by_hash: dict[str, list[FileRecord]] = {}
    for r in records:
        if r.abs_path in sensitive_handled:
            continue
        if r.sha256:
            by_hash.setdefault(r.sha256, []).append(r)

    duplicates_archived: set[str] = set()
    for h, group in by_hash.items():
        if len(group) <= 1:
            continue
        # Prefer the file with the shortest/cleanest name as winner
        group_sorted = sorted(group, key=lambda r: (
            len(r.name),
            duplicate_suffix_match(r.stem) is not None,
            sync_conflict_match(r.stem) is not None,
            r.rel_path,
        ))
        winner = group_sorted[0]
        for loser in group_sorted[1:]:
            duplicates_archived.add(loser.abs_path)
            add(
                kind="archive-duplicate",
                src=loser.abs_path,
                dst=str(root / "_Archive" / "<run-id>" / loser.rel_path),
                reason=f"exact duplicate of {winner.rel_path}",
                rule="duplicate-by-hash",
                sha256=loser.sha256, size=loser.size,
            )

    # 2) Sync-conflict and duplicate-suffix patterns where no hash match was available
    for r in records:
        if r.abs_path in duplicates_archived or r.abs_path in sensitive_handled:
            continue
        if r.sha256 is None and (sync_conflict_match(r.stem) or duplicate_suffix_match(r.stem)):
            add(
                kind="needs-human",
                src=r.abs_path,
                dst=None,
                reason="suffix suggests duplicate/conflict but file not hashed (cloud-only or too large)",
                rule="suffix-no-hash",
                sha256=None, size=r.size,
            )
            continue
        if sync_conflict_match(r.stem):
            canonical_stem = sync_conflict_match(r.stem)
            canonical_name = f"{canonical_stem}.{r.ext}" if r.ext else canonical_stem
            canonical = next((x for x in records
                              if x.name == canonical_name
                              and Path(x.rel_path).parent == Path(r.rel_path).parent), None)
            if canonical and canonical.sha256 and canonical.sha256 == r.sha256:
                add(
                    kind="archive-conflict",
                    src=r.abs_path,
                    dst=str(root / "_Archive" / "<run-id>" / r.rel_path),
                    reason=f"sync conflict; identical to {canonical.rel_path}",
                    rule="sync-conflict-resolved",
                    sha256=r.sha256, size=r.size,
                )
            else:
                add(
                    kind="needs-human",
                    src=r.abs_path,
                    dst=None,
                    reason="sync conflict with content drift; user picks winner",
                    rule="sync-conflict-drift",
                    sha256=r.sha256, size=r.size,
                )

    # 3) Default-name files with no clear category go to needs-human
    handled = {a.src for a in actions}
    for r in records:
        if r.abs_path in handled:
            continue
        if has_default_name(r.stem) and not r.category:
            add(
                kind="needs-human",
                src=r.abs_path,
                dst=None,
                reason="default scanner/app name and category cannot be inferred from path",
                rule="default-name-unknown-category",
                sha256=r.sha256, size=r.size,
            )

    # 4) Files Claude does not have a confident move for default to a non-action
    handled = {a.src for a in actions}
    for r in records:
        if r.abs_path in handled:
            continue
        # No proposed taxonomy-driven move from the script — that's a
        # conversation-driven step. Surface unclassified files so the
        # conductor can ask the user.
        if not r.category:
            add(
                kind="needs-human",
                src=r.abs_path,
                dst=None,
                reason="no category match; conductor to classify with user",
                rule="unclassified",
                sha256=r.sha256, size=r.size,
            )

    return actions


def write_plan(root: Path, records: list[FileRecord], actions: list[Action],
               plan_md: Path, plan_json: Path) -> None:
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    payload = {
        "run_id": run_id,
        "root": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "files_scanned": len(records),
            "files_cloud_only": sum(1 for r in records if r.is_cloud_only),
            "files_hashed": sum(1 for r in records if r.sha256),
            "files_sensitive": sum(1 for r in records if r.is_sensitive),
        },
        "actions": [asdict(a) for a in actions],
    }
    plan_json.write_text(json.dumps(payload, indent=2))

    by_kind: dict[str, list[Action]] = {}
    for a in actions:
        by_kind.setdefault(a.kind, []).append(a)

    lines = [
        f"# Cleanup plan",
        f"",
        f"- Root: `{root}`",
        f"- Generated: {payload['generated_at']}",
        f"- Run id: `{run_id}`",
        f"",
        f"## Counts",
        f"",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Files scanned | {payload['counts']['files_scanned']} |",
        f"| Files cloud-only (not hashed) | {payload['counts']['files_cloud_only']} |",
        f"| Files hashed | {payload['counts']['files_hashed']} |",
        f"| Sensitive (default skip) | {payload['counts']['files_sensitive']} |",
        f"",
        f"## Actions by category",
        f"",
        f"| Kind | Count |",
        f"|---|---|",
    ]
    for kind in ("rename", "move", "archive-duplicate", "archive-conflict", "skip", "needs-human"):
        lines.append(f"| {kind} | {len(by_kind.get(kind, []))} |")
    lines.append("")

    for kind in ("archive-duplicate", "archive-conflict", "rename", "move", "needs-human", "skip"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines.append(f"## {kind} ({len(items)})")
        lines.append("")
        for a in items:
            lines.append(f"- **#{a.id}** `{Path(a.src).name}` — {a.reason} _(rule: {a.rule})_")
            lines.append(f"    - src: `{a.src}`")
            if a.dst:
                lines.append(f"    - dst: `{a.dst}`")
        lines.append("")
    plan_md.write_text("\n".join(lines))


def cmd_analyze(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: root not found or not a directory: {root}", file=sys.stderr)
        return 2
    plan_md = Path(args.plan_out).resolve()
    plan_json = Path(args.plan_json).resolve()
    hash_cap = args.hash_cap_mb * 1024 * 1024
    print(f"walking {root} ...", file=sys.stderr)
    records = walk_tree(root, hash_cap)
    print(f"  {len(records)} files, {sum(1 for r in records if r.sha256)} hashed", file=sys.stderr)
    actions = propose_actions(root, records)
    print(f"  {len(actions)} proposed actions", file=sys.stderr)
    write_plan(root, records, actions, plan_md, plan_json)
    print(f"wrote {plan_md}")
    print(f"wrote {plan_json}")
    return 0


# --- Phase 2: dry-run ----------------------------------------------------

def load_plan(plan_json: Path) -> dict:
    return json.loads(plan_json.read_text())


def dst_for_run(dst_template: str | None, run_id: str) -> str | None:
    if dst_template is None:
        return None
    return dst_template.replace("<run-id>", run_id)


def cmd_dry_run(args: argparse.Namespace) -> int:
    plan = load_plan(Path(args.plan_json).resolve())
    run_id = plan["run_id"]
    root = Path(plan["root"])
    report_path = Path(args.report).resolve()

    targets: dict[str, list[Action]] = {}
    drift: list[Action] = []
    invalid: list[tuple[Action, str]] = []
    safe: list[Action] = []
    skipped: list[Action] = []

    for a_dict in plan["actions"]:
        a = Action(**a_dict)
        if a.kind in ("skip", "needs-human"):
            skipped.append(a)
            continue
        # Drift check: did the file change since the plan was written?
        src = Path(a.src)
        if not src.exists():
            invalid.append((a, "src-missing"))
            continue
        try:
            cur_size = src.stat().st_size
        except OSError as e:
            invalid.append((a, f"stat-failed: {e}"))
            continue
        if a.size is not None and cur_size != a.size:
            drift.append(a)
            continue
        # Destination validity
        dst = dst_for_run(a.dst, run_id)
        if dst is None:
            invalid.append((a, "no destination"))
            continue
        rel = Path(dst).relative_to(root) if str(dst).startswith(str(root)) else Path(dst).name
        err = validate_dest_path(root, str(rel))
        if err:
            invalid.append((a, err))
            continue
        targets.setdefault(dst, []).append(a)
        safe.append(a)

    collisions = {k: v for k, v in targets.items() if len(v) > 1 or Path(k).exists()}

    lines = [
        f"# Dry-run report",
        f"",
        f"- Plan run id: `{run_id}`",
        f"- Root: `{root}`",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"",
        f"## Summary",
        f"",
        f"| Status | Count |",
        f"|---|---|",
        f"| Safe to execute | {len(safe)} |",
        f"| Skipped (skip + needs-human) | {len(skipped)} |",
        f"| Drift (file changed since analyze) | {len(drift)} |",
        f"| Invalid (path / state issues) | {len(invalid)} |",
        f"| Collisions (multiple actions, same dst) | {len(collisions)} |",
        f"",
    ]
    if collisions:
        lines.append("## Collisions (BLOCK execute until resolved)")
        lines.append("")
        for dst, group in collisions.items():
            lines.append(f"- `{dst}`")
            for a in group:
                lines.append(f"    - #{a.id} {a.kind} from `{a.src}`")
            if Path(dst).exists():
                lines.append(f"    - **already exists on disk**")
        lines.append("")
    if drift:
        lines.append("## Drift (file changed since analyze)")
        lines.append("")
        for a in drift:
            lines.append(f"- #{a.id} `{a.src}` (re-run analyze)")
        lines.append("")
    if invalid:
        lines.append("## Invalid")
        lines.append("")
        for a, err in invalid:
            lines.append(f"- #{a.id} {err} — `{a.src}`")
        lines.append("")
    report_path.write_text("\n".join(lines))
    print(f"wrote {report_path}")
    if collisions or drift or invalid:
        print("dry-run: NOT clean — fix issues before execute", file=sys.stderr)
        return 1
    print("dry-run: clean — safe to execute")
    return 0


# --- Phase 3: execute ----------------------------------------------------

def safe_move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise FileExistsError(str(dst))
    shutil.move(str(src), str(dst))


def cmd_execute(args: argparse.Namespace) -> int:
    plan = load_plan(Path(args.plan_json).resolve())
    run_id = plan["run_id"]
    root = Path(plan["root"])
    log_path = Path(args.log).resolve()

    if log_path.exists() and not args.force:
        print(f"error: log already exists at {log_path} — refusing to overwrite", file=sys.stderr)
        return 2

    moves: list[dict] = []
    errors: list[dict] = []

    # Sort so archives go first (frees up destination slots for moves/renames)
    order = {"archive-duplicate": 0, "archive-conflict": 1, "move": 2, "rename": 3}
    actions = sorted(
        (Action(**a) for a in plan["actions"] if a["kind"] in order),
        key=lambda a: order[a.kind],
    )

    for a in actions:
        dst_str = dst_for_run(a.dst, run_id)
        if dst_str is None:
            errors.append({"id": a.id, "src": a.src, "error": "no destination"})
            continue
        src, dst = Path(a.src), Path(dst_str)
        if not src.exists():
            errors.append({"id": a.id, "src": a.src, "error": "src missing at execute time"})
            continue
        try:
            sha = a.sha256 or (sha256_file(src) if src.stat().st_size <= HASH_SIZE_CAP_BYTES else None)
            safe_move(src, dst)
            moves.append({
                "id": a.id, "kind": a.kind,
                "from": str(src), "to": str(dst),
                "sha256": sha, "at": datetime.now().isoformat(timespec="seconds"),
            })
        except Exception as e:
            errors.append({"id": a.id, "src": a.src, "error": f"{e.__class__.__name__}: {e}"})
            break  # stop on first error so undo target is clear

    log = {
        "run_id": run_id,
        "root": str(root),
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "moves": moves,
        "errors": errors,
    }
    log_path.write_text(json.dumps(log, indent=2))
    print(f"wrote {log_path}: {len(moves)} moves, {len(errors)} errors")
    return 1 if errors else 0


# --- Phase 4: undo -------------------------------------------------------

def cmd_undo(args: argparse.Namespace) -> int:
    log_path = Path(args.log).resolve()
    log = json.loads(log_path.read_text())
    reversed_moves: list[dict] = []
    errors: list[dict] = []
    # Reverse in opposite order of execution
    for mv in reversed(log["moves"]):
        src, dst = Path(mv["to"]), Path(mv["from"])
        if not src.exists():
            errors.append({"id": mv["id"], "error": "destination of original move is missing", "path": str(src)})
            continue
        try:
            safe_move(src, dst)
            reversed_moves.append({"id": mv["id"], "from": str(src), "to": str(dst)})
        except Exception as e:
            errors.append({"id": mv["id"], "error": f"{e.__class__.__name__}: {e}", "path": str(src)})
            break
    out = {
        "undone_at": datetime.now().isoformat(timespec="seconds"),
        "moves_reversed": reversed_moves,
        "errors": errors,
    }
    consumed = log_path.with_suffix(f".{datetime.now().strftime('%Y%m%d%H%M%S')}.undone.json")
    log_path.rename(consumed)
    consumed.write_text(json.dumps({**log, "undo_result": out}, indent=2))
    print(f"reversed {len(reversed_moves)} moves; log consumed -> {consumed}")
    return 1 if errors else 0


# --- CLI -----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cleanup")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="Walk and plan")
    a.add_argument("--root", required=True)
    a.add_argument("--taxonomy", required=False, help="Path to taxonomy reference (informational)")
    a.add_argument("--plan-out", required=True)
    a.add_argument("--plan-json", required=True)
    a.add_argument("--hash-cap-mb", type=int, default=500)
    a.set_defaults(func=cmd_analyze)

    d = sub.add_parser("dry-run", help="Simulate the plan")
    d.add_argument("--plan-json", required=True)
    d.add_argument("--report", required=True)
    d.set_defaults(func=cmd_dry_run)

    e = sub.add_parser("execute", help="Apply the plan")
    e.add_argument("--plan-json", required=True)
    e.add_argument("--log", required=True)
    e.add_argument("--force", action="store_true", help="Overwrite existing log")
    e.set_defaults(func=cmd_execute)

    u = sub.add_parser("undo", help="Reverse a previous execute")
    u.add_argument("--log", required=True)
    u.set_defaults(func=cmd_undo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
