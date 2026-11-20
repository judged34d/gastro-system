# Builds offline Gastro-System setup.exe (Python + wheels embedded)
$ErrorActionPreference = 'Stop'
$InstallerDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $InstallerDir '..')
$Staging = Join-Path $InstallerDir 'staging'
$Dist = Join-Path $InstallerDir 'dist'
$Build = Join-Path $InstallerDir 'build'
$OutExe = Join-Path $Dist 'setup.exe'
$Offline = Join-Path $InstallerDir 'offline'
$StickDir = Join-Path $Dist 'USB-Stick'
$PyOffline = Join-Path $Offline 'python-3.12.10-amd64.exe'
$WheelsDir = Join-Path $Offline 'wheels'

Write-Host ('Repo: ' + $RepoRoot)
Write-Host ('Staging: ' + $Staging)

$whlCount = @(Get-ChildItem $WheelsDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count
$needFetch = (-not (Test-Path $PyOffline)) -or ($whlCount -lt 1)
if ($needFetch) {
    Write-Host 'Offline-Bundle fehlt - hole Abhaengigkeiten ...'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallerDir 'fetch-offline-deps.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'fetch-offline-deps.ps1 fehlgeschlagen' }
    $whlCount = @(Get-ChildItem $WheelsDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count
}
if (-not (Test-Path $PyOffline)) { throw ('Python-Installer fehlt: ' + $PyOffline) }
if ($whlCount -lt 1) { throw ('Keine Wheels in ' + $WheelsDir) }
Write-Host ('Offline-Bundle OK: Python-Installer + ' + $whlCount + ' Wheels')

Write-Host 'Vorab-Verifikation (Offline-Frischinstallation) ...'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallerDir 'verify-offline-install.ps1')
if ($LASTEXITCODE -ne 0) { throw 'verify-offline-install.ps1 fehlgeschlagen – setup.exe wird NICHT gebaut' }

foreach ($dir in @($Dist, $Build, $Staging)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
$excludeDirs = @('.git', 'venv', '.venv', '__pycache__', 'installer\staging', 'installer\build', 'installer\dist', 'data')
Get-ChildItem -Path $RepoRoot -Force | ForEach-Object {
    $name = $_.Name
    if ($excludeDirs -contains $name) { return }
    if ($name -eq 'installer') {
        $resSrc = Join-Path $_.FullName 'resources'
        $resDst = Join-Path $Staging 'installer_resources'
        if (Test-Path $resSrc) {
            Copy-Item $resSrc $resDst -Recurse -Force
        }
        return
    }
    Copy-Item $_.FullName (Join-Path $Staging $name) -Recurse -Force
}

$offlineGuide = Join-Path $RepoRoot 'data\Anleitung-Offline-Betrieb.html'
if (Test-Path $offlineGuide) {
    $guideDest = Join-Path $Staging 'data'
    New-Item -ItemType Directory -Path $guideDest -Force | Out-Null
    Copy-Item $offlineGuide (Join-Path $guideDest 'Anleitung-Offline-Betrieb.html') -Force
}

$payload = Join-Path $InstallerDir 'payload'
if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
Copy-Item $Staging $payload -Recurse -Force

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw 'Python nicht gefunden. Bitte Python 3 installieren.' }

& $py.Source -m pip install --upgrade pip pyinstaller --quiet
Set-Location $InstallerDir

$wizard = Join-Path $InstallerDir 'gastro_setup_wizard.py'
$sep = ';'
$addPayload = $payload + $sep + 'payload'
$addRes = (Join-Path $InstallerDir 'resources') + $sep + 'resources'
$addOffline = $Offline + $sep + 'offline'
$pyArgs = @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onefile',
    '--windowed',
    '--name', 'gastro-setup-tmp',
    '--distpath', $Dist,
    '--workpath', $Build,
    '--specpath', $InstallerDir,
    '--add-data', $addPayload,
    '--add-data', $addRes,
    '--add-data', $addOffline,
    '--hidden-import', 'setup_prereqs',
    '--hidden-import', 'install_handbook',
    $wizard
)
Write-Host ('PyInstaller start...')
& $py.Source @pyArgs
if ($LASTEXITCODE -ne 0) { throw ('PyInstaller ExitCode ' + $LASTEXITCODE) }

$built = Join-Path $Dist 'gastro-setup-tmp.exe'
if (-not (Test-Path $built)) { throw ('Build fehlgeschlagen: ' + $built + ' fehlt') }

Get-ChildItem -Path $Dist -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
if (Test-Path $OutExe) { Remove-Item $OutExe -Force }
Get-ChildItem -Path $Dist -Filter '*.exe' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'gastro-setup-tmp.exe' } |
    Remove-Item -Force

Move-Item -Path $built -Destination $OutExe -Force

New-Item -ItemType Directory -Path $StickDir -Force | Out-Null
Copy-Item $OutExe (Join-Path $StickDir 'setup.exe') -Force
if (Test-Path $offlineGuide) {
    Copy-Item $offlineGuide (Join-Path $StickDir 'Anleitung-Offline-Betrieb.html') -Force
}

$lesenLines = @(
    'Gastro-System - USB-Stick (Offline-Installation)',
    '================================================',
    '',
    'NUR DIESE setup.exe vom Stick verwenden (neueste Version).',
    '',
    'Bei vorheriger Fehlinstallation: Setup einfach erneut ausfuehren',
    '(venv wird neu aufgebaut). Alten Stick-Inhalt vorher ersetzen.',
    '',
    '1. setup.exe Doppelklick -> UAC mit JA bestaetigen (Administrator).',
    '2. Cloudflare Tunnel: AUS lassen (Haken nicht setzen).',
    '3. LAN-IP des Gastro-PCs waehlen (z.B. 192.168.178.x) und IP pruefen.',
    '4. Installationsordner bestaetigen (Standard ist OK) -> Installieren.',
    '5. Warten bis Meldung Installation abgeschlossen (2-5 Minuten, KEIN Internet).',
    '6. Desktop-Link Gastro-System oeffnen -> Gastro-System starten.',
    '7. Status: Backend + Datenbank + Frontend gruen/ok.',
    '8. Tablets gleiches WLAN (kein Gastnetz): http://<LAN-IP>:8081/',
    '',
    'Anleitung-Offline-Betrieb.html = Event anlegen, Theken, QR, Betrieb.',
    '',
    'Inkscape darf installiert sein - Gastro nutzt NUR das eigene venv,',
    'niemals Python aus dem PATH.',
    '',
    'Deinstallieren: Desktop Gastro deinstallieren',
    'oder Windows-Einstellungen -> Apps -> Gastro-System.'
)
[System.IO.File]::WriteAllLines((Join-Path $StickDir 'LIESMICH.txt'), $lesenLines)

$sizeMb = [math]::Round((Get-Item $OutExe).Length / 1MB, 1)
Write-Host ''
Write-Host ('Fertig: ' + $OutExe + ' (' + [string]$sizeMb + ' MB)')
Write-Host ('USB-Inhalt: ' + $StickDir)
Write-Host '  - setup.exe'
Write-Host '  - Anleitung-Offline-Betrieb.html'
Write-Host '  - LIESMICH.txt'
