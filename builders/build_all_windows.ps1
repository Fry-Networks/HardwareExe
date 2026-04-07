param(
  [string[]] $Codes = @("BM","IDM","ODM","ISM","OSM","SVN","SDN","RDN","AEM","IRM"),
  [string]   $Version = "6.1.5",
  [int]$VersionCheckSec = 600,
  [switch]$Sign = $false,
  [string]$SignPfxPath = "",
  [string]$SignPfxPassword = "",
  [string]$SignSubject = "",
  [string]$SignTimestampUrl = "http://timestamp.digicert.com",
  [string]$CompanyName = "Fry Networks LLC",
  [string]$ProductName = "",
  [string]$FileDescription = ""
)

py -m pip install --upgrade pip
py -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib h3 pillow shapely geoip2

# ---------- Metadata Mapping ----------
$MetaByCode = @{
  'BM'  = @{ ProductName = 'Fry Networks Bandwidth Miner';  FileDescription = 'Fry Networks Bandwidth Miner' }
  'IDM' = @{ ProductName = 'Fry Networks Indoor Decibel Miner';    FileDescription = 'Fry Networks Indoor Decibel Miner' }
  'ODM' = @{ ProductName = 'Fry Networks Outdoor Decibel Miner';    FileDescription = 'Fry Networks Outdoor Decibel Miner' }
  'ISM' = @{ ProductName = 'Fry Networks Indoor Satellite Miner';  FileDescription = 'Fry Networks Indoor Satellite Miner' }
  'OSM' = @{ ProductName = 'Fry Networks Outdoor Satellite Miner';  FileDescription = 'Fry Networks Outdoor Satellite Miner' }
  'RDN' = @{ ProductName = 'Fry Networks Reward Decentralization Node';      FileDescription = 'Fry Networks Reward Decentralization Node' }
  'SDN' = @{ ProductName = 'Fry Networks Storage Decentralization Node';     FileDescription = 'Fry Networks Storage Decentralization Node' }
  'SVN' = @{ ProductName = 'Fry Networks Storage Validator Node';   FileDescription = 'Fry Networks Storage Validator Node' }
  'AEM' = @{ ProductName = 'Fry Networks AI Edge Miner';    FileDescription = 'Fry Networks AI Edge Miner' }
  'IRM' = @{ ProductName = 'Fry Networks Radiation Miner';  FileDescription = 'Fry Networks Radiation Miner' }
}
function Get-ExecutableMetadata {
  param(
    [Parameter(Mandatory)][string]$Code,
    [Parameter(Mandatory)][string]$CompanyName,
    [string]$OverrideProductName = "",
    [string]$OverrideFileDescription = ""
  )
  $base = $MetaByCode[$Code.ToUpper()]
  if (-not $base) {
    $base = @{ ProductName = "Fry Networks $Code"; FileDescription = "Fry Networks component $Code." }
  }
  @{
    CompanyName    = $CompanyName
    ProductName    = if ($OverrideProductName) { $OverrideProductName } else { $base.ProductName }
    FileDescription= if ($OverrideFileDescription) { $OverrideFileDescription } else { $base.FileDescription }
  }
}

# ---------- PyInstaller Version File Writer ----------
function New-VersionFile {
  <#
    Creates a temporary version resource file for PyInstaller (--version-file).
    Returns: full path to the version file.
  #>
  param(
    [Parameter(Mandatory)][string]$Path,
    [Parameter(Mandatory)][string]$CompanyName,
    [Parameter(Mandatory)][string]$ProductName,
    [Parameter(Mandatory)][string]$FileDescription,
    [Parameter(Mandatory)][string]$FileVersion,     # e.g., 5.3.0
    [Parameter(Mandatory)][string]$InternalName,    # e.g., FRY_PoC_BM_v5.3.0
    [Parameter(Mandatory)][string]$OriginalFilename # e.g., FRY_PoC_BM_v5.3.0.exe
  )

  # Convert semantic version "5.3.0" to "5,3,0,0" for VSVersionInfo
  $verParts = ($FileVersion -split '\.') + @('0','0','0','0')
  $verTuple = ($verParts[0..3] | ForEach-Object { [int]$_ }) -join ', '

  $content = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($verTuple),
    prodvers=($verTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'$CompanyName'),
            StringStruct(u'FileDescription', u'$FileDescription'),
            StringStruct(u'FileVersion', u'$FileVersion'),
            StringStruct(u'InternalName', u'$InternalName'),
            StringStruct(u'OriginalFilename', u'$OriginalFilename'),
            StringStruct(u'ProductName', u'$ProductName'),
            StringStruct(u'ProductVersion', u'$FileVersion'),
            StringStruct(u'LegalCopyright', u'© $(Get-Date -Format yyyy) $CompanyName')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@

  try {
  Set-Content -Path $Path -Value $content -NoNewline -Encoding utf8NoBOM
  } catch {
    # Fallback for PS 5.1: write via .NET to avoid BOM
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $content, $utf8NoBom)
  }
}


# PFX password must be provided directly if signing is enabled; 1Password is not used.

if (-not (Test-Path ".\nssm.exe")) {
  Write-Warning "nssm.exe (x64) not found in project root. NSSM is expected to be provided by the external installer; continuing without bundling NSSM."
}

foreach ($Code in $Codes) {
  Write-Host "=== Building $Code v$Version ==="
  
  # Generate config_profile.py with the specified version
  $makeProfile = Join-Path $PSScriptRoot '..\miner_GUI\tools\make_profile.py'
  if (Test-Path $makeProfile) {
    & py $makeProfile --code $Code --version $Version --version-check-sec $VersionCheckSec
  } else {
    Write-Warning "make_profile.py not found at $makeProfile; skipping profile generation step."
  }

  # Get metadata for this code
  $meta = Get-ExecutableMetadata -Code $Code -CompanyName $CompanyName -OverrideProductName $ProductName -OverrideFileDescription $FileDescription

  # ---------- Inject BM Mysterium secrets from 1Password ----------
  # Secrets are provided via installer-managed miner_config.enc; no embedding in build.

  # ----- Icon resolution & conversion (supports .ico, .png, .jpg) -----
  $iconBase = switch ($Code.ToUpper()) { 'BM'{'BM'} 'IDM'{'DB'} 'ODM'{'DB'} 'ISM'{'GNSS'} 'OSM'{'GNSS'} 'RDN'{'NODE'} 'SVN'{'NODE'} 'SDN'{'NODE'} 'AEM'{'AEM'} 'IRM' {'RAD'} default{'frynetworks_logo'} }
  $IconDir  = Join-Path $PWD 'images'
  $IconIco  = Join-Path $IconDir "$iconBase.ico"
  $IconPng  = Join-Path $IconDir "$iconBase.png"
  $IconJpg  = Join-Path $IconDir "$iconBase.jpg"

  # ---------- Build GUI ----------
  $GuiName = "FRY_${Code}_v${Version}"
  $guiDistDir = Join-Path $PWD ("dist\gui\${Code}")
  $qif = (& py -c "import os,PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins', 'imageformats'))" 2>$null)
  $havePlugins = ($qif -and (Test-Path (Join-Path $qif 'qjpeg.dll')))
  $guiArgs = @('--clean','--onefile','--noconsole','--noconfirm','--name', $GuiName,'--hidden-import','PySide6.QtNetwork','--add-data','images;images','--add-data','qt.conf;.','--distpath', $guiDistDir)
  # Simplified GUI: Only charts module needed
  $guiArgs += @(
    '--hidden-import','miner_GUI.ui.widgets.charts',
    '--collect-data','matplotlib',
    '--hidden-import','matplotlib.backends.backend_qtagg',
    '--hidden-import','matplotlib.backends.backend_qt5agg'
  )
  # Attach icon if available
  if ($IconIco -and (Test-Path $IconIco)) { $guiArgs += @('-i', $IconIco) }
  if ($havePlugins) {
    # Add only the imageformat plugin files that actually exist to avoid build failures
    $plugins = @('qjpeg.dll','qpng.dll','qico.dll','qsvg.dll')
    foreach ($pl in $plugins) {
      $candidate = Join-Path $qif $pl
      if (Test-Path $candidate) {
        $guiArgs += @('--hidden-import','miner_GUI.LiveData','--add-data', ("$candidate;PySide6/plugins/imageformats"))
      }
    }
    # If no individual plugin was added, fall back to collecting PySide6 so images still load
    $added = $false
    foreach ($arg in $guiArgs) { if ($arg -match 'PySide6/plugins/imageformats') { $added = $true; break } }
    if (-not $added) { $guiArgs += @('--collect-all','PySide6','--collect-all','miner_GUI.LiveData') }
  } else {
    $guiArgs += @('--collect-all','PySide6','--collect-all','miner_GUI.LiveData')
  }
  # Exclude pymongo (EXE uses External API via HTTP only)
  $excludes = @('--exclude-module','pymongo')
  switch ($Code) {
    'BM'  { $excludes += @('--exclude-module','sounddevice','--exclude-module','serial') }
    'AEM' { $excludes += @('--exclude-module','sounddevice','--exclude-module','serial') }
    'IDM' { $excludes += @('--exclude-module','serial') }
    'ODM' { $excludes += @('--exclude-module','serial') }
    'ISM' { $excludes += @('--exclude-module','sounddevice') }
    'OSM' { $excludes += @('--exclude-module','sounddevice') }
    'SVN' { $excludes += @('--exclude-module','sounddevice','--exclude-module','serial') }
    'SDN' { $excludes += @('--exclude-module','sounddevice','--exclude-module','serial') }
    'RDN' { $excludes += @('--exclude-module','sounddevice','--exclude-module','serial') }
  }
  $guiArgs += $excludes
  # Add version info to GUI exe
  $guiVerFile = Join-Path $PWD ("_tmp_version_gui_${Code}.txt")
  New-VersionFile -Path $guiVerFile `
                  -CompanyName $meta.CompanyName `
                  -ProductName $meta.ProductName `
                  -FileDescription $meta.FileDescription `
                  -FileVersion $Version `
                  -InternalName $GuiName `
                  -OriginalFilename ("{0}.exe" -f $GuiName) | Out-Null
  $guiArgs += @('--version-file', $guiVerFile)

  py -m PyInstaller @guiArgs main.py

  # Sign outputs (optional)
  if ($Sign) {
    function Get-SignTool { $st = Get-Command signtool.exe -ErrorAction SilentlyContinue; if ($st) { return $st.Path }; return $null }
    function Invoke-CodeSigning {
      param([string]$Path)
      if (-not (Test-Path $Path)) { return }
      $signtool = Get-SignTool
      if (-not $signtool) { Write-Warning "signtool.exe not found; skipping signing for $Path"; return }
      $signArgs = @('sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr', $SignTimestampUrl)
      if ($SignPfxPath) {
        $signArgs += @('/f', $SignPfxPath)
        if ($SignPfxPassword) { $signArgs += @('/p', $SignPfxPassword) }
      } elseif ($SignSubject) {
        $signArgs += @('/n', $SignSubject)
      }
      $signArgs += $Path
      & $signtool @signArgs | Write-Verbose
    }
    $guiBuilt = Join-Path $guiDistDir ("{0}.exe" -f $GuiName)
    if (Test-Path $guiBuilt) { Invoke-CodeSigning -Path $guiBuilt }
  }

  # Move to release
  $out = "release\$Version"
  New-Item -ItemType Directory -Force -Path $out | Out-Null
  $guiBuilt = Join-Path $guiDistDir ("{0}.exe" -f $GuiName)
  if (Test-Path $guiBuilt) { Move-Item -Force $guiBuilt "$out\$GuiName.exe" }

  # Clean up version file
  Remove-Item -Force $guiVerFile -ErrorAction SilentlyContinue

  # Clean up embedded secrets file so secrets are not left in workspace; restore a placeholder for IDE linting
  # No embedded secrets file to clean up; secrets are read from miner_config.enc at runtime.
}

Write-Host "All builds complete."

