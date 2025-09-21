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

$VersionTagName = "$Tag-v$Version"
$VersionReleaseTitle = "$Tag - $Version"
$VersionAssetName = "FRY-$Tag-v$Version.exe"

function Test-GitCleanTree {
  $wd = git diff --name-only
  $idx = git diff --cached --name-only
  if ($wd -or $idx) {
    throw "Working tree not clean. Commit or stash changes first."
  }
}

function Test-GhReleaseExists {
  param([Parameter(Mandatory=$true)][string]$ReleaseName)
  try {
    gh release view $ReleaseName --json name *> $null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  } finally {
    if ($LASTEXITCODE -ne 0) { $global:LASTEXITCODE = 0 }
  }
}

# --- Basic checks ---
git rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Not in a git repo." }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI 'gh' not found. Install and run 'gh auth login'."
}

Test-GitCleanTree

# --- Save old pointer for rollback ---
$OldPointer = $null
git rev-parse -q --verify "refs/tags/$Tag" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
  $OldPointer = (git rev-parse -q --verify $Tag)
  Write-Host "Old $Tag now points to $OldPointer"
}

# --- Ensure version tag does not exist ---
git rev-parse -q --verify "refs/tags/$VersionTagName" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
  throw "Tag $VersionTagName already exists. Choose a new version or delete it first."
}

# --- Create & push the immutable version tag on HEAD ---
git tag -a $VersionTagName -m "Release $VersionReleaseTitle"
git push $Remote $VersionTagName

# --- Move & push the moving tag ---
git tag -f $Tag $VersionTagName
git push $Remote -f $Tag

# --- Ensure release exists for version tag ---
$versionReleaseExists = Test-GhReleaseExists -ReleaseName $VersionTagName
if ($versionReleaseExists) {
  gh release edit $VersionTagName --title "$VersionReleaseTitle" --notes "Release $VersionReleaseTitle"
} else {
  gh release create $VersionTagName --title "$VersionReleaseTitle" --notes "Release $VersionReleaseTitle"
}

# --- Ensure Release exists for moving tag and set title/notes ---
$releaseExists = Test-GhReleaseExists -ReleaseName $Tag
$movingReleaseNotes = "Latest $Tag release: $Version"
if ($releaseExists) {
  gh release edit $Tag --title "$Tag" --notes "$movingReleaseNotes"
} else {
  gh release create $Tag --title "$Tag" --notes "$movingReleaseNotes"
}

# --- Remove previous executables for this moving tag so auto-update only grabs the latest build ---
$cleanupPattern = "^FRY-" + [regex]::Escape($Tag) + "-.*\.exe$"
$existingAssets = @()
try {
  $assetsJson = gh release view $Tag --json assets 2>$null
  if ($assetsJson) {
    $existingAssets = ($assetsJson | ConvertFrom-Json).assets
    foreach ($asset in $existingAssets) {
      $name = $asset.name
      $asset_id = $asset.id
      if ($name -match $cleanupPattern -and $name -ne $VersionAssetName) {
        try {
          gh release delete-asset $Tag $asset_id --yes | Out-Null
          Write-Host "Removed old asset: $name"
        } catch {
          Write-Warning "Failed to remove asset '$name': $($_.Exception.Message)"
        }
      }
    }
  }
} catch {
  Write-Warning "Unable to list existing assets for ${Tag}: $($_.Exception.Message)"
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
        Write-Host "Other candidates (newest to oldest, excluded shown separately if any):"
        $tailLimit = [Math]::Min($Candidates.Count - 1, 4)
        if ($tailLimit -gt 0) {
          $Candidates[1..$tailLimit] | ForEach-Object { " - " + $_.FullName } | Write-Output
        }
      }
    } else {
      Write-Warning "No matching artifacts found in '$BuildDir' (Include='$IncludeGlob', Exclude='$ExcludeRegex'). Skipping upload."
    }
  }
}

# --- Upload chosen artifact (if any) ---
if ($ChosenArtifact) {
  $desiredName = $VersionAssetName
  $currentName = [System.IO.Path]::GetFileName($ChosenArtifact)
  $uploadPath = $ChosenArtifact
  $tempDir = $null
  if ($currentName -ne $desiredName) {
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("release-upload-" + [System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    $uploadPath = Join-Path $tempDir $desiredName
    Copy-Item -Path $ChosenArtifact -Destination $uploadPath -Force
  }
  try {
    gh release upload $VersionTagName $uploadPath --clobber
    Write-Host "Uploaded to ${VersionTagName}: $desiredName"

    gh release upload $Tag $uploadPath --clobber
    Write-Host "Uploaded to ${Tag}: $desiredName"
  } finally {
    if ($tempDir -and (Test-Path $tempDir)) {
      try { Remove-Item -Path $tempDir -Force -Recurse -ErrorAction SilentlyContinue } catch {}
    }
  }
} else {
  Write-Warning "No artifact uploaded."
}

@"
Done!

Created version tag:   $VersionTagName
Updated moving tag:    $Tag now points to $VersionTagName
Remote:                $Remote
Version release:       $VersionTagName (title: $VersionReleaseTitle)
Moving release:        $Tag (latest asset: $VersionAssetName)

Rollback:
  git tag -f $Tag $OldPointer
  git push $Remote -f $Tag
"@ | Write-Output
