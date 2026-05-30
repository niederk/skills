# Handoff to Claude Code CLI

Paste this entire document as your first message to a fresh Claude Code session. It tells the new session what was built in a prior Cowork session, where it lives on GitHub, and what to do.

---

## For the receiving Claude Code session — read carefully

A prior Claude session (in Cowork web) helped me build a custom skill called `folder-cleanup` for tidying messy client engagement folders on OneDrive/SharePoint. The skill is committed and pushed to a branch on GitHub. Your job is to:

1. Detect my OS and install the skill onto this machine.
2. Verify it loaded.
3. Walk me through the first real-data run when I'm ready.

### Context you should know

- I'm at Percipio Business Advisors (PBA). The skill targets PBA client folders on OneDrive/SharePoint.
- The skill does **plan → dry-run → execute → undo** with archive-don't-delete, sensitive-file guards (signed/efiled/IRS notices default to skip), OneDrive sync-conflict detection, and deduplication by SHA-256.
- **There is no codified PBA folder taxonomy yet.** The skill surfaces unclassified files as `needs-human` instead of inventing structure. We discover the working taxonomy per engagement in Phase 0.
- The first real-data run is reconnaissance only — `analyze` produces a markdown plan that I review before anything is moved.

### Repo and branch

- GitHub repo: `niederk/skills`
- Branch: `claude/custom-file-cleanup-skill-0k131`
- Skill path within the repo: `skills/folder-cleanup/`

### Step 1: Ask which OS I'm on, then install

Run the appropriate install command. **Do not run both.**

**Mac/Linux:**
```bash
git clone --depth 1 --branch claude/custom-file-cleanup-skill-0k131 \
  https://github.com/niederk/skills.git /tmp/skills-clone && \
mkdir -p ~/.claude/skills && \
cp -r /tmp/skills-clone/skills/folder-cleanup ~/.claude/skills/ && \
rm -rf /tmp/skills-clone
```

**Windows (PowerShell):**
```powershell
git clone --depth 1 --branch claude/custom-file-cleanup-skill-0k131 `
  https://github.com/niederk/skills.git $env:TEMP\skills-clone
New-Item -ItemType Directory -Force -Path $env:USERPROFILE\.claude\skills | Out-Null
Copy-Item -Recurse -Force $env:TEMP\skills-clone\skills\folder-cleanup `
  $env:USERPROFILE\.claude\skills\
Remove-Item -Recurse -Force $env:TEMP\skills-clone
```

**Fallback if `git` isn't installed:** download the branch ZIP from `https://github.com/niederk/skills/archive/refs/heads/claude/custom-file-cleanup-skill-0k131.zip`, extract, and copy `skills-claude-custom-file-cleanup-skill-0k131/skills/folder-cleanup` into `~/.claude/skills/` (Mac/Linux) or `%USERPROFILE%\.claude\skills\` (Windows).

### Step 2: Verify install

Confirm the script runs:

```bash
python3 ~/.claude/skills/folder-cleanup/scripts/cleanup.py --help
```

(On Windows, use `python` instead of `python3` if `python3` isn't on PATH.)

Tell me to type `/skills` in Claude Code to confirm `folder-cleanup` is listed.

### Step 3: Wait for me to give you a folder path

When I give you an absolute path to a client folder, **run analyze only**. Do not run dry-run or execute on real client data until I've reviewed the plan and explicitly approved it.

The pre-flight checklist is at `~/.claude/skills/folder-cleanup/FIRST_RUN.md` — read it before the first run.

### Boundaries — important

- Never run `execute` or `dry-run` without me explicitly asking.
- Never delete files — the skill archives, not deletes. If you ever consider `rm` or `Remove-Item`, stop and ask.
- Do not push changes to the GitHub branch (`claude/custom-file-cleanup-skill-0k131`) without my explicit OK. The skill files installed at `~/.claude/skills/` are local only.
- If the plan flags signed tax returns, e-filed forms, or IRS notices, surface them prominently. Do not let them get archived by accident — they default to `skip` in the rules, and that's intentional.
- Treat each client engagement as a sealed unit. Do not carry naming conventions or quirks from one client to another unless I say so.

### What to do right now

1. Ask me which OS I'm on (Mac, Windows, or Linux).
2. Run the appropriate install command.
3. Verify with `python3 ~/.claude/skills/folder-cleanup/scripts/cleanup.py --help`.
4. Ask me whether I want to (a) just stop here and run it later, or (b) proceed to Phase 0 onboarding for a specific client folder right now. If (b), ask me for the absolute path.

That's the handoff. The skill's SKILL.md will take over once it's triggered by a real cleanup request.
