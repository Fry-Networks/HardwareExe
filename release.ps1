Param(
  [Parameter(Mandatory=$true)][string]$Version,      # e.g. 5.0.1
  [Parameter(Mandatory=$true)][string]$Tag,          # e.g. BM
  [string]$Remote = "origin",
  [string]$ArtifactGlob = "dist/*.exe"
)

$ErrorActionPreference = "Stop"

function Ensure-CleanTree {
  $wd = git diff --name-only
  $idx = git diff --cached --name-only
  if ($wd -or $idx) {
    throw "Working tree not clean. Commit or stash changes first."
  }
}

# Checks
git rev-parse --is-inside-work-tree *> $null | Out-Null
if (-not $?) { throw "Not in a git repo." }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI 'gh' not found. Install and run 'gh auth login'."
}

Ensure-CleanTree

# Save old pointer (for rollback)
$OldPointer = $null
if (git rev-parse -q --verify "refs/tags/$Tag" *> $null) {
  $OldPointer = (git rev-parse -q --verify $Tag)
  Write-Host "Old $Tag -> $OldPointer"
}

# Ensure version tag doesn't exist
if (git rev-parse -q --verify "refs/tags/$Version" *> $null) {
  throw "Tag $Version already exists. Choose a new version or delete it first."
}

# Create & push version tag
git tag -a $Version -m "Release $Version"
git push $Remote $Version

# Move & push moving tag
git tag -f $Tag $Version
git push $Remote -f $Tag

# Create/Edit release
if (gh release view $Tag *> $null) {
  gh release edit $Tag --title "$Version" --notes "Release $Version"
} else {
  gh release create $Tag --title "$Version" --notes "Release $Version"
}

# Expand glob and upload artifacts
$Artifacts = Get-ChildItem -Path $ArtifactGlob -File -ErrorAction SilentlyContinue
if (-not $Artifacts) {
  Write-Warning "No artifacts matched '$ArtifactGlob'. Skipping upload."
} else {
  $Paths = $Artifacts.FullName
  gh release upload $Tag $Paths --clobber
  Write-Host "✅ Uploaded: $($Paths -join ', ')"
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
