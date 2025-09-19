param(
  [Parameter(Mandatory=$true)][string]$Code,
  [Parameter(Mandatory=$true)][string]$Version,
  [int]$VersionCheckSec = 60,
  [switch]$Use1Password = $true,
  [switch]$UseGithub = $true,
  [string]$OPRefMongoURI = "op://Mongo/Dude350zTest-Vercel/uri",
  [string]$OPRefSigningKey = "op://VSCode/hardware_exe/local_signing_key_hex",
  [string]$OPRefUpdateRepo = "op://VSCode/hardware_exe/Github_repo_test",
  [string]$OPRefGithubToken = "op://VSCode/hardware_exe/Github_token",
  [string]$GithubToken = "",
  [bool]$SoftwareUptodate = $true,
  [int]$IntervalSeconds = 600,
  [string]$TlsCAFile = "",
  [switch]$Sign = $false,
  [string]$SignPfxPath = "",
  [SecureString]$SignPfxPassword = $null,
  [string]$SignSubject = "",
  [string]$SignTimestampUrl = "http://timestamp.digicert.com",
  [switch]$Use1PasswordPfx = $false,
  [string]$OPRefPfxPassword = "",
  [switch]$Open1P = $false
)

py -m pip install --upgrade pip
py -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib pymongo h3 pillow shapely geoip2

function Test-HexKey { param([string]$Hex)
  if (-not $Hex) { return $false }
  if ($Hex -notmatch '^[0-9a-fA-F]{64}$') { return $false }
  try { [void][Convert]::ToByte($Hex.Substring(0,2),16); return $true } catch { return $false }
}
function Mask-Key { param([string]$Hex)
  if (-not $Hex) { return '-' }
  try { return ("{0}�{1}" -f $Hex.Substring(0,6), $Hex.Substring(58)) } catch { return '-' }
}

# Optional: 1Password helpers for PFX password (opt-in)
if ($Use1PasswordPfx -and $Sign -and $SignPfxPath -and (-not $SignPfxPassword) -and $OPRefPfxPassword) {
  if (-not (Get-Command op -ErrorAction SilentlyContinue)) { Write-Error "1Password CLI 'op' not found on PATH."; exit 1 }
  try {
    $pwPlain = (& op read $OPRefPfxPassword).Trim()
    if (-not $pwPlain) { throw "Empty password read from 1Password reference: $OPRefPfxPassword" }
    $SignPfxPassword = ConvertTo-SecureString $pwPlain -AsPlainText -Force
  } catch { Write-Error "Failed to read PFX password from 1Password: $_"; exit 1 }
}
if ($Open1P -and $OPRefPfxPassword) {
  if (-not (Get-Command op -ErrorAction SilentlyContinue)) { Write-Error "1Password CLI 'op' not found on PATH."; exit 1 }
  try {
    $ref = $OPRefPfxPassword -replace '^op://',''
    $parts = $ref -split '/'
    if ($parts.Length -ge 2) { & op item get $parts[1] --vault $parts[0] --open | Out-Null }
  } catch {}
}

# Ensure images folder + background.jpg
try {
  $imgDir = Join-Path $PSScriptRoot 'images'
  New-Item -ItemType Directory -Force -Path $imgDir | Out-Null
  foreach ($s in @('background.png','frynetworks_logo.png','FryNetworks_logo.png')) {
    $srcImg = Join-Path $PSScriptRoot $s
    if (Test-Path $srcImg) { Copy-Item -Force $srcImg (Join-Path $imgDir $s) }
  }
  $bgPng = Join-Path $imgDir 'background.png'
  if (Test-Path $bgPng) {
    $bgJpg = Join-Path $imgDir 'background.jpg'
    py -c "from PIL import Image; import sys; im=Image.open(sys.argv[1]).convert('RGB'); im.save(sys.argv[2], quality=90)" "$bgPng" "$bgJpg" 2>$null
  }
} catch {}

$toolProfile = Join-Path $PSScriptRoot 'tools\make_profile.py'
if (-not $VersionCheckSec) { $VersionCheckSec = 600 }
py $toolProfile --code $Code --version $Version --version-check-sec $VersionCheckSec

# Embed encrypted config into miner_online_simple.py (via tools/make_encrypted_config.py)
$patched = $false
if ($Use1Password) {
  if (-not (Get-Command op -ErrorAction SilentlyContinue)) { Write-Error "1Password CLI 'op' not found on PATH."; exit 1 }
  if (-not $OPRefMongoURI) { Write-Error "Provide -OPRefMongoURI like op://Vault/Item/mongo_uri"; exit 1 }
  try {
    $mongoUri = (& op read $OPRefMongoURI).Trim(); if (-not $mongoUri) { throw "Empty mongo URI from 1Password" }
    $tmpCfg = Join-Path $PSScriptRoot "_tmp_config.json"
    $cfg = @{ mongo_uri = $mongoUri; interval_seconds = $IntervalSeconds; use_github = [bool]$UseGithub }
    if ($UseGithub) { $cfg.github_token = '' }
    $cfg.software_uptodate = [bool]$SoftwareUptodate
    if ($TlsCAFile) { $cfg.tlsCAFile = [IO.Path]::GetFileName($TlsCAFile) }
    if ($OPRefSigningKey) {
      $signKey = (& op read $OPRefSigningKey).Trim(); if (-not $signKey) { throw "Empty signing key from 1Password" }
      if (-not (Test-HexKey $signKey)) { throw "Signing key must be 64 hex chars (32 bytes)" }
      $cfg.local_signing_key_hex = $signKey
      Write-Host ("Signing key OK (fingerprint {0})" -f (Mask-Key $signKey))
    }
    if ($OPRefUpdateRepo) {
      $repo = (& op read $OPRefUpdateRepo).Trim();
      if (-not $repo -or ($repo -notmatch '/')) { throw "Update repo must be 'owner/repo'" }
      $cfg.update_repo = $repo
      # Enforce signing key when setting update_repo
      $signKey = (& op read $OPRefSigningKey).Trim();
      if (-not $signKey) { throw "Empty signing key from 1Password" }
      if (-not (Test-HexKey $signKey)) { throw "Signing key must be 64 hex chars (32 bytes)" }
      $cfg.local_signing_key_hex = $signKey
      Write-Host ("Signing key OK (fingerprint {0})" -f (Mask-Key $signKey))
    }
    if ($UseGithub) {
      $githubTok = ''
      if ($OPRefGithubToken) {
        $githubTok = (& op read $OPRefGithubToken).Trim()
      } elseif ($GithubToken) {
        $githubTok = $GithubToken.Trim()
      }
      if (-not $githubTok) { throw "Provide GitHub token via -OPRefGithubToken or -GithubToken when -UseGithub is set" }
      $cfg.github_token = $githubTok
    }
    $cfg | ConvertTo-Json -Compress | Set-Content -Encoding UTF8 $tmpCfg

    $encTool = Join-Path $PSScriptRoot 'tools\make_encrypted_config.py'
    $enc = & py $encTool --in $tmpCfg --json; if ($LASTEXITCODE -ne 0) { throw "Failed to run make_encrypted_config.py" }
    $json = ConvertFrom-Json ($enc | Out-String); $dlt=$json.dlt; $dlp=$json.dlp; $knt=$json.knt; $knp=$json.knp
    $srcPath = Join-Path $PSScriptRoot "miner_online_simple.py"
    $bakPath = "$srcPath.bak"
    Copy-Item -Force $srcPath $bakPath
    $srcText = Get-Content -Path $srcPath -Raw -Encoding UTF8
    $pattern = "^(\s*)dlt=b''; dlp=b''; knt=b''; knp=b''\s*$"
    $matches = [regex]::Matches($srcText, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if ($matches.Count -eq 0) { throw "Placeholder line not found in miner_online_simple.py" }
    $newText = [regex]::Replace(
      $srcText,
      $pattern,
      { param($m) ($m.Groups[1].Value + "dlt=$dlt; dlp=$dlp; knt=$knt; knp=$knp") },
      [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    Set-Content -Path $srcPath -Value $newText -Encoding UTF8
    $patched = $true
  } catch { Write-Error "1Password embedding failed: $_"; exit 1 }
}

function Get-SignTool {
  $st = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($st) { return $st.Path }
  $kits = "C:\\Program Files (x86)\\Windows Kits\\10\\bin","C:\\Program Files (x86)\\Windows Kits\\8.1\\bin"
  foreach ($k in $kits) { if (Test-Path $k) { $cand = Get-ChildItem -Path $k -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue | Select-Object -First 1; if ($cand) { return $cand.FullName } } }
  return $null
}
function Invoke-CodeSigning { param([string]$Path)
  if (-not $Sign) { return }
  if (-not (Test-Path $Path)) { return }
  $signtool = Get-SignTool; if (-not $signtool) { Write-Warning "signtool.exe not found; skipping signing for $Path"; return }
  $sigArgs = @('sign','/fd','SHA256','/td','SHA256','/tr', $SignTimestampUrl)
  $pwdPlain = $null
  if ($SignPfxPassword) { $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SignPfxPassword); try { $pwdPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) } } }
  if ($SignPfxPath) { $sigArgs += @('/f', $SignPfxPath); if ($pwdPlain) { $sigArgs += @('/p', $pwdPlain) } }
  elseif ($SignSubject) { $sigArgs += @('/n', $SignSubject) } else { $sigArgs += @('/a') }
  $sigArgs += @($Path); & $signtool @sigArgs | Write-Verbose
}

# Build Service (PyInstaller)
$SvcName = "FRY_PoC_${Code}_v${Version}"
$svcArgs = @('--clean','--onefile','--noconsole','--noconfirm','--name', $SvcName, '--collect-binaries','h3','--collect-all','shapely','--collect-all','geoip2')
$iconBase = switch ($Code.ToUpper()) { 'BM'{'BM'} 'IDM'{'DB'} 'ODM'{'DB'} 'ISM'{'GNSS'} 'OSM'{'GNSS'} 'RDN'{'NODE'} 'SVN'{'NODE'} 'SDN'{'NODE'} default{'FryNetworks_logo'} }
$IconJpg = Join-Path $PSScriptRoot "images\$iconBase.jpg"; $IconIco = Join-Path $PSScriptRoot "images\$iconBase.ico"
if (Test-Path $IconJpg) { try { py -c "from PIL import Image; import sys; Image.open(sys.argv[1]).save(sys.argv[2], format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" "$IconJpg" "$IconIco" 2>$null } catch {} }
if (Test-Path $IconIco) { $svcArgs += @('-i', $IconIco) }
$geoLiteCandidates = @()
if ($env:MAXMIND_DB_PATH) { $geoLiteCandidates += $env:MAXMIND_DB_PATH }
$geoLiteCandidates += @(Join-Path $PSScriptRoot 'GeoLite2-Country.mmdb')
$geoLitePath = $null
foreach ($candidate in $geoLiteCandidates) {
    if (-not $candidate) { continue }
    try {
        $resolved = Resolve-Path $candidate -ErrorAction Stop
        if (Test-Path $resolved) { $geoLitePath = $resolved; break }
    } catch {}
}
if ($geoLitePath) {
    $svcArgs += @('--add-data', ("{0};." -f $geoLitePath))
    Write-Host "Bundling GeoLite2 database from $geoLitePath"
} else {
    Write-Warning "GeoLite2-Country.mmdb not found; runtime country checks will require external MAXMIND_DB_PATH"
}
if ($TlsCAFile) { $svcArgs += @('--add-data', ("{0};." -f $TlsCAFile)) }
py -m PyInstaller @svcArgs (Join-Path $PSScriptRoot 'miner_online_simple.py')
$svcExe = Join-Path (Join-Path $PSScriptRoot 'dist') ("{0}.exe" -f $SvcName); if (Test-Path $svcExe) { Invoke-CodeSigning -Path $svcExe }

# Build GUI
$GuiName = "FRY_${Code}_v${Version}"; if (-not (Test-Path (Join-Path $PSScriptRoot 'nssm.exe'))) { Write-Error "nssm.exe (x64) not found in project root. Place it here."; exit 1 }
$qif = (& py -c "import os,PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins', 'imageformats'))" 2>$null)
$havePlugins = ($qif -and (Test-Path (Join-Path $qif 'qjpeg.dll')))
$guiArgs = @('--clean','--onefile','--noconsole','--noconfirm','--name', $GuiName,'--hidden-import','PySide6.QtNetwork','--add-data',((Join-Path $PSScriptRoot 'images') + ';images'),'--add-data',((Join-Path $PSScriptRoot 'qt.conf') + ';.'),'--add-binary',(($svcExe) + ';embedded'),'--add-binary',((Join-Path $PSScriptRoot 'nssm.exe') + ';embedded'))
if (Test-Path $IconIco) { $guiArgs += @('-i', $IconIco) }
if ($havePlugins) { $guiArgs += @('--hidden-import','LiveData','--add-data', ("$qif\\qjpeg.dll;PySide6/plugins/imageformats"),'--add-data', ("$qif\\qico.dll;PySide6/plugins/imageformats")) } else { $guiArgs += @('--collect-all','PySide6','--collect-all','LiveData') }
$excludes = @('--exclude-module','pymongo'); switch ($Code) { 'BM'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial')} 'AEM'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial')} 'IDM'{$excludes += @('--exclude-module','serial')} 'ODM'{$excludes += @('--exclude-module','serial')} 'ISM'{$excludes += @('--exclude-module','sounddevice')} 'OSM'{$excludes += @('--exclude-module','sounddevice')} 'SVN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} 'SDN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} 'RDN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} }
$guiArgs += $excludes
py -m PyInstaller @guiArgs (Join-Path $PSScriptRoot 'miner_control.py')
$guiExe = Join-Path (Join-Path $PSScriptRoot 'dist') ("{0}.exe" -f $GuiName); if (Test-Path $guiExe) { Invoke-CodeSigning -Path $guiExe }

Write-Host "Built GUI: dist\$GuiName.exe"
Write-Host "Built SVC: dist\$SvcName.exe (embedded into GUI)"

if ($patched) { try { Move-Item -Force (Join-Path $PSScriptRoot 'miner_online_simple.py.bak') (Join-Path $PSScriptRoot 'miner_online_simple.py'); Remove-Item -Force (Join-Path $PSScriptRoot '_tmp_config.json') -ErrorAction SilentlyContinue } catch {} }






