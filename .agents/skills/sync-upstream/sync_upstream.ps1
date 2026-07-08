param(
    [switch]$Sync = $false,
    [switch]$Status = $false
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

Write-Host "`n=== SYNC UPSTREAM ===" -ForegroundColor Cyan
Write-Host "Repo : $RepoRoot"
Write-Host "Fork : origin (RhapsyDev/pyeventbt)"
Write-Host "Upstream: upstream (marticastany/pyeventbt)`n" -ForegroundColor Gray

Set-Location -LiteralPath $RepoRoot

# --- 1. fetch upstream ---
Write-Host "[1/5] Fetching upstream..." -ForegroundColor Yellow
git fetch upstream --prune 2>$null
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

# --- helpers ---
function Show-BehindAhead($branch) {
    $behind = git rev-list --count "origin/$branch..upstream/$branch" 2>$null
    $ahead  = git rev-list --count "upstream/$branch..origin/$branch" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  $branch : unable to compare (branch may not exist)" -ForegroundColor DarkYellow
        return
    }
    if ($behind -eq 0 -and $ahead -eq 0) {
        Write-Host "  $branch : up to date" -ForegroundColor Green
    } else {
        if ([int]$behind -gt 0) {
            Write-Host "  $branch : $behind commit(s) BEHIND upstream/$branch" -ForegroundColor Red
        }
        if ([int]$ahead -gt 0) {
            Write-Host "  $branch : $ahead commit(s) AHEAD (your local changes)" -ForegroundColor Green
        }
    }
}

# --- 2. show status ---
Write-Host "[2/5] Current status:" -ForegroundColor Yellow
Write-Host "  Active branch: $(git branch --show-current)" -ForegroundColor White
Show-BehindAhead "develop"
Show-BehindAhead "main"

# --- 3. show upstream log ---
$upstream_log = git log "HEAD..upstream/develop" --oneline -5 2>$null
if ($upstream_log) {
    Write-Host "`n  Latest upstream commits (not in local):" -ForegroundColor DarkYellow
    $upstream_log | ForEach-Object { Write-Host "    $_" }
}

# --- if --sync ---
if (-not $Sync) {
    Write-Host "`nTo sync: run with -Sync flag (e.g. & sync_upstream.ps1 -Sync)" -ForegroundColor Cyan
    Write-Host "`n=== DONE (status only) ===" -ForegroundColor Cyan
    return
}

Write-Host "`n[3/5] Stashing any local changes..." -ForegroundColor Yellow
git stash push -m "auto-stash before upstream sync" 2>$null

$currentBranch = git branch --show-current

# --- 4. sync develop ---
Write-Host "[4/5] Syncing develop branch..." -ForegroundColor Yellow
git checkout develop 2>$null
try {
    git merge upstream/develop --no-edit 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Merge conflict on develop! Resolve manually then re-run." }
    git push origin develop 2>$null
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    git merge --abort 2>$null
    git checkout $currentBranch 2>$null
    throw $_
}

# --- 5. sync current branch (la que estaba activa al iniciar) ---
Write-Host "[5/5] Syncing $currentBranch branch..." -ForegroundColor Yellow
git checkout $currentBranch 2>$null
try {
    git merge develop --no-edit 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Merge conflict on $currentBranch! Resolve manually." }
    git push origin $currentBranch 2>$null
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    git merge --abort 2>$null
    throw $_
}

# --- restore stash if any ---
$stash = git stash list 2>$null
if ($stash -match "auto-stash before upstream sync") {
    Write-Host "Restoring stashed changes..." -ForegroundColor Yellow
    git stash pop 2>$null
}

Write-Host "`n=== SYNC COMPLETE ===" -ForegroundColor Green
git log --oneline -3
