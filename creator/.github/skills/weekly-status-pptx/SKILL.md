---
name: weekly-status-pptx
description: >
  Generate a Fabric Skills weekly status PowerPoint deck from ADO work items, git history,
  and open PRs in the gim-home/skills-for-fabric and microsoft/skills-for-fabric repos, then
  upload it to the team's SharePoint folder. Use this skill whenever the user asks for a
  "weekly summary", "status slides", "status deck", "weekly pptx", "weekly report pptx", or
  mentions creating presentation slides for Fabric Skills status. Also trigger when the user
  says "generate slides", "status PowerPoint", or "upload status to SharePoint".
---

# Weekly Status PPTX

Generate a styled 7-slide PowerPoint deck summarizing Fabric Skills team activity
(merged PRs, open PR review status, test infrastructure progress, ADO User Stories),
then upload it to the team's SharePoint folder.

This is a meta-skill for the skills-for-fabric core team. It assumes you are running from
a clone of `gim-home/skills-for-fabric` with a sibling clone of `microsoft/skills-for-fabric`
for the public release diff.

## Slide Structure

| # | Slide | Content |
|---|-------|---------|
| 1 | **Title** | "Fabric Skills" · date range · 1-line top-line highlights |
| 2 | **Milestones & KPIs** | 8 milestone cards (left, board priority) + 5-KPI stack (right). Cards show DONE/NEW delta badge, status pill, ETA pill |
| 3 | **Test Infrastructure** | Same card+KPI layout as slide 2 — feature-focused: eval framework, smoke harness, release automation, CI hardening. Omit bug fixes and routine release-admin PRs |
| 4 | **Skill PRs Merged This Week** | Table: PR, Title, Category (Skill/Release/Eval/CI/Infra — color-coded), Author |
| 5 | **Open Skill PRs — Review Status** | Table: PR#, Title, Author, Status (Reviewed / New This Week / Needs Review). Header summary: Reviewed X of Y · Not ready N · Awaiting M · K new arrivals |
| 6 | **ADO Status** | Active User Stories with clickable ADO links, status, owner, ETA. Optional `↳` sub-rows for supporting merged PRs |
| 7 | **Next Week** | Numbered focus items for the coming week |

## Prerequisites

| Tool / Setup | Why |
|---|---|
| `python` and `gh` CLI on PATH | Generator runs in Python; `gh` is used for PR queries |
| `python-pptx` and `lxml` | Install: `pip install python-pptx lxml` |
| `gh auth status` shows access to `gim-home/skills-for-fabric` | For PR queries on the internal repo |
| Clone of `microsoft/skills-for-fabric` available locally | For public-release diff (path configurable via `SFF_PUBLIC_REPO` env var) |
| `az` CLI logged in (`az login`) | For ADO and Microsoft Graph (SharePoint) access tokens |
| Corp network or VPN | ADO and SharePoint endpoints require it |

## Workflow

### Step 1: Gather Inputs

Ask the user for:

1. **Date range** — default: past week (Mon–Sun)
2. **Team members** — default: Avi Sander, Matan Schaumberg, Shay Markanty
3. **New milestones or corrections** — present last week's milestones and ask if any changed
4. **Risk overrides** — any items that should deviate from "On Track"

### Step 2: Collect Data

Run all commands from the root of the `gim-home/skills-for-fabric` clone.

#### 2a. Git History

```powershell
git fetch origin --quiet
git log --since="{start}" --until="{end}" origin/main --oneline `
  --format="%h %an %ad %s" --date=short
```

#### 2b. New vs Updated Skills

Classify skills changed in the period as New or Updated:

```powershell
$N = <commits since start>
$changed = git diff --name-only "origin/main~$N..origin/main" -- "skills/" |
           ForEach-Object { ($_ -split '/')[1] } | Sort-Object -Unique
$prevSkills = git ls-tree --name-only "origin/main~$N" "skills/" |
              ForEach-Object { ($_ -split '/')[1] } | Sort-Object -Unique
$new = $changed | Where-Object { $_ -notin $prevSkills }
$upd = $changed | Where-Object { $_ -in $prevSkills }
```

#### 2c. Open Skill PRs

```powershell
gh pr list --state open --json number,title,author,reviews --limit 50
```

Count only **skill-specific PRs** — exclude infra/tooling PRs (eval runners, common/ changes,
auto-generation tools, CI/CD framework, dashboards). The user's count is authoritative if
they correct you.

For the review status slide, check if any team member (Shay, Matan, Teddy, Avi) has
reviewed each PR. Show a single status column with `✔ Reviewed` / `New This Week` /
`Needs Review`. Do NOT use individual reviewer name columns.

#### 2d. Merged PRs

```powershell
gh pr list --state merged --search "merged:>={start_date}" `
  --json number,title,author,mergedAt --limit 30
```

#### 2e. ADO Work Items

**Critical: Filter by tag `skills-for-fabric`** — the area path contains items for multiple
workstreams. Only items tagged `skills-for-fabric` belong in this deck.

```powershell
$token = az account get-access-token --resource 499b84ac-1321-427f-aa17-267ca6975798 `
  --query accessToken -o tsv
$headers = @{Authorization="Bearer $token"; "Content-Type"="application/json"}

# Active User Stories with skills-for-fabric tag
$body = '{"query":"SELECT [System.Id],[System.Title],[System.State],[Microsoft.VSTS.Scheduling.TargetDate] FROM WorkItems WHERE [System.AreaPath] UNDER ''Trident\\ISV and ALM\\Fabric Copilot'' AND [System.WorkItemType] = ''User Story'' AND [System.State] = ''Active'' AND [System.Tags] CONTAINS ''skills-for-fabric'' ORDER BY [System.ChangedDate] DESC"}'
Invoke-RestMethod -Uri 'https://powerbi.visualstudio.com/Trident/_apis/wit/wiql?api-version=7.0' `
  -Method Post -Headers $headers -Body $body

# Child tasks for a parent (non-closed, skip Design/E2E tests)
$body = '{"query":"SELECT [System.Id],[System.Title],[System.State] FROM WorkItems WHERE [System.Parent] = {parentId} AND [System.Title] NOT IN (''Design'',''E2E tests'') AND [System.State] <> ''Closed'' ORDER BY [System.Id]"}'
```

- **Area Path**: `Trident\ISV and ALM\Fabric Copilot`
- **Tag filter**: `skills-for-fabric` (mandatory)
- **State filter**: Active only — do NOT show Closed or New User Stories
- **ADO link format**: `https://powerbi.visualstudio.com/Trident/_workitems/edit/{ID}`
- **ETA**: Use `Microsoft.VSTS.Scheduling.TargetDate`. Show date for User Stories, blank for child tasks
- Skip generic child tasks named "Design" or "E2E tests"

#### 2f. Public Release Version

Diff against the previous tag to count new vs updated skills in the latest release.
Default path for the public clone is `..\skills-for-fabric-public`; override with
`$env:SFF_PUBLIC_REPO`.

```powershell
$pubRepo = if ($env:SFF_PUBLIC_REPO) { $env:SFF_PUBLIC_REPO } else { "..\skills-for-fabric-public" }
Push-Location $pubRepo
git fetch origin --quiet
git tag -l   # shows version tags
Pop-Location
```

### Step 3: Generate the PPTX

Copy the bundled `generate-weekly-summary.py` template to a working directory of your
choice (e.g. a gitignored `.local/weekly/` folder), rename it to
`generate-weekly-{YYYY-MM-DD}.py`, and fill in the blocks marked `# EDIT ME`.

```powershell
python .local\weekly\generate-weekly-2026-06-08.py
```

The deck is written to the same folder as the script. `python-pptx` produces clean OOXML
natively, so no post-processing is required.

#### Design Tokens

Two-tier palette: **vivid colors** for text/accents, **muted fills** for backgrounds and pills.
Text is the primary signal; pills are secondary chrome.

```python
C = {
    # Vivid text + accents
    "navy":      "1E2761",  # headings
    "darkText":  "1E293B",
    "muted":     "64748B",
    "accent":    "3B82F6",  # KPI numbers, hyperlinks
    "green":     "16A34A",  # KPI numbers, Done text
    "amber":     "D97706",  # KPI numbers, WIP text
    "red":       "DC2626",
    "teal":      "0891B2",  # category color: Skill

    # Muted fills + chrome
    "navyFill":  "3F5485",  # title-slide bg + number circles
    "offWhite":  "F7F9FC",  # content slide bg
    "white":     "FFFFFF",
    "ice":       "E3EAF5",  # subtitle text on dark bg + ETA pill bg
    "tableHead": "5E6F94",
    "tableRow1": "FAFBFD",
    "tableRow2": "F1F5FB",

    # Status / delta pill fills (muted to keep text accents primary)
    "greenFill":  "7FB39A",  # Completed / In Progress / DONE delta
    "amberFill":  "D9B36A",  # Not Started
    "redFill":    "C58585",  # Blocked
    "tealFill":   "8FB8C4",
    "accentFill": "7DA0D6",  # accent bars + NEW delta
}
FONT_HEADER = "Georgia"
FONT_BODY = "Calibri"
```

#### Slide-by-Slide Notes

**Slide 1 (Title)**: `navyFill` background, top + bottom accent bars (`accentFill`, 0.06"
height), large Georgia title (48pt), Calibri subtitle with date range, italic 1-line
top-line highlights.

**Slide 2 (Milestones & KPIs)**: Off-white background. 8 milestone cards on the left in
board priority order, 5-KPI stack on the right (positions `KPI_Y = [0.95, 1.85, 2.75, 3.65, 4.55]`,
each `2.5×0.85`).

Card anatomy (left → right): 0.07" status-color accent bar · navy number circle (0.30×0.30) ·
title + 1-line desc · **delta badge** (DONE/NEW, only if applicable) · **status pill** ·
**ETA pill**.

- **Delta badge** (`0.55×0.22`, 7pt): green-fill for `DONE`, accent-fill for `NEW`. Omit for
  carryover items. Small and secondary to the status pill.
- **Status pill** (`0.95×0.32`, 9pt): muted fill from `STATUS.{notStarted|inProgress|completed|blocked}`.
- **ETA pill** (`1.03×0.32`, 9pt): outlined `ice` fill with `tableHead` border + `navy` bold
  text. Visually distinct from the filled status pill.

5 KPIs (typical): Skill PRs Reviewed (X/Y) · PRs Merged this week · Total Public Skills ·
Skills Awaiting Public · Latest Public Release. Use vivid `C.accent / C.green / C.amber / C.teal`
for the big number, 7pt italic muted sub-line below.

**Slide 3 (Test Infrastructure)**: Identical card + KPI layout as slide 2 (reuse via the
`renderCardsAndKpis()` helper in the template). **Feature-focused** — include only material
feature contributions (eval framework, smoke harness, release automation, CI hardening).
**Omit pure bug fixes and routine release-admin PRs.**

Typical mix: 5 shipped this week + 3 in-flight DRAFTs with `NEW` delta. KPIs: Features
Shipped · Features In Flight · Major eval surface (e.g., "Phase 2") · Smoke Run Failures ·
Next Drop date.

**Slide 4 (PRs Merged This Week)**: Table — PR, Title, Category, Author. **Category color
coding** (text color, bold): Skill=`teal` · Release=`accent` · Eval=`accent` · CI=`amber` ·
Infra=`green`. Subtitle splits total into skill content vs infrastructure.

Column widths: `[0.85, 5.45, 1.3, 2.0]`, row height `0.27`. ~15 rows fit.

**Slide 5 (Open PR Review Status)**: Header summary: `Reviewed X of Y · Not ready: Z ·
Awaiting review: N · M new arrivals this week`. Table — PR#, Title, Author, Status.
Status color: `✔ Reviewed`=green · `New This Week`=teal · `Needs Review`=amber. Optional
overflow line below the table for additional PRs not worth showing in full.

Column widths: `[0.7, 5.0, 1.8, 1.3]`, row height `0.30`. ~12 rows fit.

**Slide 6 (ADO Status)**: 5-column table — #, Item, Status, Owner, ETA. User Story titles
are bold hyperlinks (`adoLink` cell options). Optional `↳` sub-row beneath a US to list
supporting child tasks or merged PRs (use `cellOpts` with green color). ETA color:
`amber`=this month, `teal`=next month+. **Only Active items** with the `skills-for-fabric`
tag — no Closed or New. Optional green-italic "Closed this week" callout below the table.

Column widths: `[0.35, 5.45, 1.1, 0.9, 1.05]`, row height `0.32`.

**Slide 7 (Next Week)**: `navyFill` background, accent bars, numbered circles
(`accentFill`) with white text, 4–5 short focus items in `ice` text.

### Step 4: Open for Review

```powershell
Start-Process .\Fabric-Skills-Weekly-{YYYY-MM-DD}.pptx
```

The user typically provides 2–5 rounds of corrections. The generation script stays on disk
for fast re-runs: edit → regenerate → reopen.

**Important**: Close PowerPoint before regenerating — file-lock error otherwise. Wrap each
regenerate in:

```powershell
Get-Process POWERPNT -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
Start-Sleep -Milliseconds 800
python generate-weekly-{YYYY-MM-DD}.py
Start-Process .\Fabric-Skills-Weekly-{YYYY-MM-DD}.pptx
```

#### Reordering slides safely

When a corrected slide order is requested (e.g. "move slide 5 to slide 3"), do **not** edit
slide blocks individually — variable collisions in 3-cycles are easy to miss. Instead,
write a small helper that:

1. Reads the whole generator file (UTF-8).
2. Splits it on the `# SLIDE N` comment headers.
3. Renames `\bsN\b` variables and the comment headers per block (word-boundary regex).
4. Concatenates the blocks in the new order and writes the result back.

Verify first with grep for `\bs[3-7]\b` to confirm slide variables are used only within
their own block and won't collide with strings/comments.

### Step 5: Upload to SharePoint

```powershell
$token = az account get-access-token --resource https://graph.microsoft.com --query accessToken -o tsv
$driveId = "b!aYuMUObXEk6IBsfLDeuHxCvOflCiwtJMvekgcUYf_eUxdnFHZjrWQ6aweNEEjWgk"
$folderId = "017PLABZRVZOFLO7JBQBCZ2SYTGABOIFHP"
$fileName = "Status weekly - {YYYY-MM-DD}.pptx"
$filePath = ".\Fabric-Skills-Weekly-{YYYY-MM-DD}.pptx"
$fileBytes = [System.IO.File]::ReadAllBytes($filePath)
$uploadUrl = "https://graph.microsoft.com/v1.0/drives/$driveId/items/${folderId}:/${fileName}:/content"

Invoke-RestMethod -Uri $uploadUrl -Method Put `
  -Headers @{Authorization="Bearer $token"; "Content-Type"="application/vnd.openxmlformats-officedocument.presentationml.presentation"} `
  -Body $fileBytes
```

- **SharePoint site**: `microsofteur.sharepoint.com/teams/Fabricunifiedcopilot`
- **Folder**: `Fabric unified copilot > Status`
- **File naming**: `Status weekly - {YYYY-MM-DD}.pptx`

## Defaults

| Setting | Value |
|---|---|
| Area Path | `Trident\ISV and ALM\Fabric Copilot` |
| ADO tag | `skills-for-fabric` |
| ADO org | `powerbi.visualstudio.com` |
| ADO project | `Trident` |
| Internal repo | Current working directory (`gim-home/skills-for-fabric` clone) |
| Public repo path | `..\skills-for-fabric-public` (override via `$env:SFF_PUBLIC_REPO`) |
| Date range | Past 1 week |
| Output file name | `Fabric-Skills-Weekly-{YYYY-MM-DD}.pptx` |
| SharePoint name | `Status weekly - {YYYY-MM-DD}.pptx` |

## Avoid

- ADO items without the `skills-for-fabric` tag — the area path has items for other workstreams
- Closed or New (inactive) ADO User Stories — only show Active
- Feature-level ADO items (too high-level)
- Generic child tasks like "Design" or "E2E tests" (noise)
- Counting git branches as PRs — use `gh pr list` for real PR counts
- Individual reviewer name columns — use a single "Status" / "Pending Comments" column
- Long descriptions — keep language short and direct
- "Unmerged branches" terminology — just say "open PRs"
- Pure bug-fix or routine release-admin PRs on the Test Infrastructure slide — feature contributions only
- Vivid pill fills (e.g. `green`, `red`) for status/delta — use the muted `*Fill` tokens so the text accents stay primary
- Sequential single-name renames during slide reorders — split + rename + reassemble in one pass to avoid 3-cycle collisions
- Committing generated `.pptx` decks to the repo — keep them in a gitignored working folder
