param(
  [string[]] $Codes = @("BM","IDM","ODM","ISM","OSM","SVN","SDN","RDN","AEM"),
  [string]   $Version = "3.9.4",
  [int]$VersionCheckSec = 600,
  [switch]$Use1Password = $false,
  [switch]$UseGithub = $false,
  [string]$OPRefMongoURI = "",
  [string]$OPRefSigningKey = "",
  [string]$OPRefUpdateRepo = "",
  [string]$OPRefGithubToken = "",
  [string]$GithubToken = "",
  [bool]$SoftwareUptodate = $true,
  [SecureString]$OPRefPfxPassword = "",
  [int]$IntervalSeconds = 600,
  [string]$TlsCAFile = "",
  [switch]$Sign = $false,
  [string]$SignPfxPath = "",
  [SecureString]$SignPfxPassword = $null,
  [string]$SignSubject = "",
  [string]$SignTimestampUrl = "http://timestamp.digicert.com",
  [switch]$Use1PasswordPfx = $false,
  [switch]$Open1P = $false,
  [string]$CompanyName = "",
  [string]$ProductName = "",
  [string]$FileDescription = ""
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
  try { return ("{0}…{1}" -f $Hex.Substring(0,6), $Hex.Substring(58)) } catch { return '-' }
}

# 1Password helpers for PFX password (opt-in)
if ($Use1PasswordPfx -and $Sign -and $SignPfxPath -and (-not $SignPfxPassword) -and $OPRefPfxPassword) {
  if (-not (Get-Command op -ErrorAction SilentlyContinue)) { Write-Error "1Password CLI 'op' not found on PATH."; exit 1 }
  try { $pwPlain = (& op read $OPRefPfxPassword).Trim(); if (-not $pwPlain) { throw "Empty password" }; $SignPfxPassword = ConvertTo-SecureString $pwPlain -AsPlainText -Force } catch { Write-Error "Failed to read PFX password: $_"; exit 1 }
}

if (-not (Test-Path ".\nssm.exe")) { Write-Error "nssm.exe (x64) not found in project root. Place it here."; exit 1 }

foreach ($Code in $Codes) {
  Write-Host "=== Building $Code v$Version ==="
  py tools\make_profile.py --code $Code --version $Version --version-check-sec $VersionCheckSec

  $patched = $false
  if ($Use1Password) {
    if (-not (Get-Command op -ErrorAction SilentlyContinue)) { Write-Error "1Password CLI 'op' not found on PATH."; exit 1 }
    if (-not $OPRefMongoURI) { Write-Error "Provide -OPRefMongoURI like op://Vault/Item/mongo_uri"; exit 1 }
    try {
      $mongoUri = (& op read $OPRefMongoURI).Trim(); if (-not $mongoUri) { throw "Empty mongo URI" }
      $tmpCfg = Join-Path $PWD "_tmp_config.json"
      $cfg = @{ mongo_uri = $mongoUri; interval_seconds = $IntervalSeconds; use_github = [bool]$UseGithub }
      if ($UseGithub) { $cfg.github_token = '' }
      $cfg.software_uptodate = [bool]$SoftwareUptodate
      if ($TlsCAFile) { $cfg.tlsCAFile = [IO.Path]::GetFileName($TlsCAFile) }
      if ($OPRefSigningKey) {
        $signKey = (& op read $OPRefSigningKey).Trim(); if (-not $signKey) { throw "Empty signing key" }
        if (-not (Test-HexKey $signKey)) { throw "Signing key must be 64 hex chars (32 bytes)" }
        $cfg.local_signing_key_hex = $signKey; Write-Host ("Signing key OK (fingerprint {0})" -f (Mask-Key $signKey))
      }
      if ($OPRefUpdateRepo) {
        $repo = (& op read $OPRefUpdateRepo).Trim(); if (-not $repo -or ($repo -notmatch '/')) { throw "Update repo must be 'owner/repo'" }
        $cfg.update_repo = $repo
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

      $enc = & py tools\make_encrypted_config.py --in $tmpCfg --json; if ($LASTEXITCODE -ne 0) { throw "Failed to run make_encrypted_config.py" }
      $json = ConvertFrom-Json ($enc | Out-String); $dlt=$json.dlt; $dlp=$json.dlp; $knt=$json.knt; $knp=$json.knp
      $srcPath = Join-Path $PWD "miner_online_simple.py"; $bakPath = "$srcPath.bak"; Copy-Item -Force $srcPath $bakPath
      $srcLines = Get-Content -Path $srcPath -Encoding UTF8
      $idx = $null; for ($i=0; $i -lt $srcLines.Count; $i++) { if ($srcLines[$i].Trim() -eq "dlt=b''; dlp=b''; knt=b''; knp=b''") { $idx = $i; break } }
      if ($idx -eq $null) { throw "Placeholder line not found in miner_online_simple.py" }
      $leading = ($srcLines[$idx] -replace '^(\s*).*','$1'); $srcLines[$idx] = "${leading}dlt=$dlt; dlp=$dlp; knt=$knt; knp=$knp"
      Set-Content -Path $srcPath -Value $srcLines -Encoding UTF8; $patched = $true
    } catch { Write-Error "1Password embedding failed: $_"; exit 1 }
  }

  # Build service
  $SvcName = "FRY_PoC_${Code}_v${Version}"; $svcDistDir = Join-Path $PWD ("dist\\svc\\${Code}")
  $svcArgs = @('--clean','--onefile','--noconsole','--noconfirm','--name', $SvcName, '--collect-binaries','h3','--collect-all','shapely','--collect-all','geoip2','--distpath', $svcDistDir)
  $iconBase = switch ($Code.ToUpper()) { 'BM'{'BM'} 'IDM'{'DB'} 'ODM'{'DB'} 'ISM'{'GNSS'} 'OSM'{'GNSS'} 'RDN'{'NODE'} 'SVN'{'NODE'} 'SDN'{'NODE'} default{'FryNetworks_logo'} }
  $IconJpg = Join-Path $PWD "images\$iconBase.jpg"; $IconIco = Join-Path $PWD "images\$iconBase.ico"
  if (Test-Path $IconJpg) { try { py -c "from PIL import Image; import sys; Image.open(sys.argv[1]).save(sys.argv[2], format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" "$IconJpg" "$IconIco" 2>$null } catch {} }
  if (Test-Path $IconIco) { $svcArgs += @('-i', $IconIco) }
  $geoLiteCandidates = @()
  if ($env:MAXMIND_DB_PATH) { $geoLiteCandidates += $env:MAXMIND_DB_PATH }
  $geoLiteCandidates += @(Join-Path $PWD 'GeoLite2-Country.mmdb')
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
  py -m PyInstaller @ $svcArgs miner_online_simple.py
  $svcBuilt = Join-Path $svcDistDir ("{0}.exe" -f $SvcName)

  # Build GUI
  $GuiName = "FRY_${Code}_v${Version}"; $guiDistDir = Join-Path $PWD ("dist\\gui\\${Code}")
  $qif = (& py -c "import os,PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins', 'imageformats'))" 2>$null)
  $havePlugins = ($qif -and (Test-Path (Join-Path $qif 'qjpeg.dll')))
  $guiArgs = @('--clean','--onefile','--noconsole','--noconfirm','--name', $GuiName,'--hidden-import','PySide6.QtNetwork','--add-data','images;images','--add-data','qt.conf;.','--add-binary',("${svcBuilt};embedded"),'--add-binary','nssm.exe;embedded','--distpath', $guiDistDir)
  if (Test-Path $IconIco) { $guiArgs += @('-i', $IconIco) }
  if ($havePlugins) { $guiArgs += @('--hidden-import','LiveData','--add-data', ("$qif\\qjpeg.dll;PySide6/plugins/imageformats"),'--add-data', ("$qif\\qico.dll;PySide6/plugins/imageformats")) } else { $guiArgs += @('--collect-all','PySide6','--collect-all','LiveData') }
  $excludes = @('--exclude-module','pymongo'); switch ($Code) { 'BM'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial')} 'AEM'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial')} 'IDM'{$excludes += @('--exclude-module','serial')} 'ODM'{$excludes += @('--exclude-module','serial')} 'ISM'{$excludes += @('--exclude-module','sounddevice')} 'OSM'{$excludes += @('--exclude-module','sounddevice')} 'SVN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} 'SDN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} 'RDN'{$excludes += @('--exclude-module','sounddevice','--exclude-module','serial','--exclude-module','matplotlib','--exclude-module','numpy')} }
  $guiArgs += $excludes
  py -m PyInstaller @ $guiArgs miner_control.py

  # Sign outputs (optional)
  if ($Sign) {
    function Get-SignTool { $st = Get-Command signtool.exe -ErrorAction SilentlyContinue; if ($st) { return $st.Path }; return $null }
    function Invoke-CodeSigning { param([string]$Path) if (-not (Test-Path $Path)) { return } $signtool = Get-SignTool; if (-not $signtool) { return }; & $signtool sign /fd SHA256 /td SHA256 /tr $SignTimestampUrl $Path | Write-Verbose }
    $guiBuilt = Join-Path $guiDistDir ("{0}.exe" -f $GuiName); if (Test-Path $guiBuilt) { Invoke-CodeSigning -Path $guiBuilt }
    if (Test-Path $svcBuilt) { Invoke-CodeSigning -Path $svcBuilt }
  }

  # Move to release
  $out = "release\$Code"; New-Item -ItemType Directory -Force -Path $out | Out-Null
  $guiBuilt = Join-Path $guiDistDir ("{0}.exe" -f $GuiName); if (Test-Path $guiBuilt) { Move-Item -Force $guiBuilt "$out\$GuiName.exe" }
  if (Test-Path $svcBuilt) { Move-Item -Force $svcBuilt "$out\$SvcName.exe" }

  if ($patched) { try { Move-Item -Force "$PWD\miner_online_simple.py.bak" "$PWD\miner_online_simple.py"; Remove-Item -Force "$PWD\_tmp_config.json" -ErrorAction SilentlyContinue } catch {} }
}

Write-Host "All builds complete."


