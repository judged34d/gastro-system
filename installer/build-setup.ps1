# Baut Gastro-System-Setup.exe (PyInstaller + eingebettetes Payload)
$ErrorActionPreference = 'Stop'
$InstallerDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $InstallerDir '..')
$Staging = Join-Path $InstallerDir 'staging'
$Dist = Join-Path $InstallerDir 'dist'
$Build = Join-Path $InstallerDir 'build'
$OutExe = Join-Path $Dist 'setup.exe'

Write-Host "Repo: $RepoRoot"
Write-Host "Staging: $Staging"

# Alte Build-Artefakte (onedir-Ordner, doppelte EXE, Zwischenstände)
foreach ($dir in @($Dist, $Build, $Staging)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
$excludeDirs = @('.git', 'venv', '.venv', '__pycache__', 'installer\staging', 'installer\build', 'installer\dist', 'data')
Get-ChildItem -Path $RepoRoot -Force | ForEach-Object {
    $name = $_.Name
    if ($excludeDirs -contains $name) { return }
    if ($name -eq 'installer') {
        Copy-Item (Join-Path $_.FullName 'resources') (Join-Path $Staging 'installer_resources') -Recurse -Force -ErrorAction SilentlyContinue
        return
    }
    Copy-Item $_.FullName (Join-Path $Staging $name) -Recurse -Force
}

# Payload-Ordner für Wizard
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
$addPayload = "$payload${sep}payload"
$addRes = "$(Join-Path $InstallerDir 'resources')${sep}resources"
$args = @(
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
    '--hidden-import', 'setup_prereqs',
    '--hidden-import', 'install_handbook',
    $wizard
)
Write-Host "PyInstaller: $($args -join ' ')"
& $py.Source @args

$built = Join-Path $Dist 'gastro-setup-tmp.exe'
if (-not (Test-Path $built)) { throw "Build fehlgeschlagen: $built fehlt" }

# Nur onedir-Müll (Ordner + alte EXE-Namen), die gebaute TMP-EXE bleibt bis zum Umbenennen
Get-ChildItem -Path $Dist -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
if (Test-Path $OutExe) { Remove-Item $OutExe -Force }
Get-ChildItem -Path $Dist -Filter '*.exe' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'gastro-setup-tmp.exe' } |
    Remove-Item -Force

Move-Item -Path $built -Destination $OutExe -Force
Write-Host ""
Write-Host "Fertig: $OutExe"
