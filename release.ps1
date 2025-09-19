Param(
  [Parameter(Mandatory=$true)][string]$Version,      # e.g. 5.0.1
  [Parameter(Mandatory=$true)][string]$Tag,          # e.g. BM
  [string]$Remote = "origin",

  # If you pass -ArtifactPath, the script will use that file directly.
  [string]$ArtifactPath = $null,

  # If ArtifactPath is not provided, the script will search this folder:
  [string]$BuildDir = "dist",

  # Include/Exclude rules for auto-discovery:
  [string]$IncludeGlob = "*.exe",
  [string]$ExcludeRegex = "^FRY_PoC.*\.exe$"  # exclude any EXE that starts with FRY_PoC
)

$ErrorActionPreference = "Stop"

function Ensure-CleanTree {
  $wd = git diff --name-only
  $idx = git diff --cached --name-only
  if ($wd -or $idx) {
    throw "Working tree not clean. Commit or stash changes first."
  }
}

# --- Basic checks ---
git rev-parse --is-inside-work-tree *> $null | Out-Null
if (-not $?) { throw "Not in a git repo." }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI 'gh' not found. Install and run 'gh auth login'."
}

Ensure-CleanTree

# --- Save old pointer for rollback ---
$OldPointer = $null
if (git rev-parse -q --verify "refs/tags/$Tag" *> $null) {
  $OldPointer = (git rev-parse -q --verify $Tag)
  Write-Host "Old $Tag -> $OldPointer"
}

# --- Ensure version tag doesn't exist ---
if (git rev-parse -q --verify "refs/tags/$Version" *> $null) {
  throw "Tag $Version already exists. Choose a new version or delete it first."
}

# --- Create & push the immutable version tag on HEAD ---
git tag -a $Version -m "Release $Version"
git push $Remote $Version

# --- Move & push the moving tag ---
git tag -f $Tag $Version
git push $Remote -f $Tag

# --- Ensure Release exists for $Tag and set title/notes to $Version ---
$releaseExists = $false
gh release view $Tag *> $null
if ($LASTEXITCODE -eq 0) {
  $releaseExists = $true
}

if ($releaseExists) {
  gh release edit $Tag --title "$Version" --notes "Release $Version"
} else {
  gh release create $Tag --title "$Version" --notes "Release $Version"
}

# --- Remove previous executables for this moving tag so auto-update only grabs the latest build ---
$cleanupPattern = "^FRY_" + [regex]::Escape($Tag) + "_.+\.exe$"
$existingAssets = @()
try {
  $existingAssets = gh release view $Tag --json assets --jq '.assets[].name'
} catch {
  Write-Warning "Unable to list existing assets for $Tag: $($_.Exception.Message)"
}
if ($existingAssets) {
  foreach ($asset in $existingAssets) {
    if ($asset -match $cleanupPattern) {
      try {
        gh release delete-asset $Tag $asset --yes | Out-Null
        Write-Host "Removed old asset: $asset"
      } catch {
        Write-Warning "Failed to remove asset '$asset': $($_.Exception.Message)"
      }
    }
  }
}

# --- Select artifact: explicit path OR auto-discover newest exe (excluding FRY_PoC*.exe) ---
$ChosenArtifact = $null

if ($ArtifactPath) {
  if (-not (Test-Path $ArtifactPath)) {
    throw "ArtifactPath not found: $ArtifactPath"
  }
  $ChosenArtifact = (Resolve-Path $ArtifactPath).Path
  Write-Host "Using provided artifact: $ChosenArtifact"
} else {
  if (-not (Test-Path $BuildDir)) {
    Write-Warning "Build directory '$BuildDir' not found. Skipping upload."
  } else {
    $Candidates = Get-ChildItem -Path $BuildDir -Filter $IncludeGlob -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -notmatch $ExcludeRegex } |
      Sort-Object LastWriteTime -Descending

    if ($Candidates -and $Candidates.Count -gt 0) {
      $ChosenArtifact = $Candidates[0].FullName
      Write-Host "Auto-selected newest artifact: $ChosenArtifact"
      if ($Candidates.Count -gt 1) {
        Write-Host "Other candidates (newest → oldest, excluded shown separately if any):"
        $Candidates[1..([Math]::Min($Candidates.Count-1,4))] | ForEach-Object { " - " + $_.FullName } | Write-Output
      }
    } else {
      Write-Warning "No matching artifacts found in '$BuildDir' (Include='$IncludeGlob', Exclude='$ExcludeRegex'). Skipping upload."
    }
  }
}

# --- Upload chosen artifact (if any) ---
if ($ChosenArtifact) {
  gh release upload $Tag $ChosenArtifact --clobber
  Write-Host "✅ Uploaded: $ChosenArtifact"
} else {
  Write-Warning "No artifact uploaded."
}

@"
✅ Done!

Created version tag:   $Version
Updated moving tag:    $Tag -> $Version
Remote:                $Remote
Release updated:       $Tag (title: $Version)

Rollback:
  git tag -f $Tag $OldPointer
  git push $Remote -f $Tag
"@ | Write-Output
