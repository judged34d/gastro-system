# Laedt Offline-Abhaengigkeiten fuer setup.exe (braucht Internet NUR auf dem Build-PC).
# Ergebnis: installer\offline\ (Python-Installer + Wheels + optional cloudflared)
$ErrorActionPreference = "Stop"
$InstallerDir = $PSScriptRoot
$Offline = Join-Path $InstallerDir "offline"
$Wheels = Join-Path $Offline "wheels"
$PyVer = "3.12.10"
$PyExeName = "python-$PyVer-amd64.exe"
$PyUrl = "https://www.python.org/ftp/python/$PyVer/$PyExeName"
$CfUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
$RepoRoot = Resolve-Path (Join-Path $InstallerDir "..")
$Req = Join-Path $RepoRoot "requirements.txt"

New-Item -ItemType Directory -Path $Wheels -Force | Out-Null

$pyDest = Join-Path $Offline $PyExeName
if (-not (Test-Path $pyDest) -or (Get-Item $pyDest).Length -lt 1MB) {
    Write-Host "Lade Python-Installer ($PyVer) ..."
    Invoke-WebRequest -Uri $PyUrl -OutFile $pyDest -UseBasicParsing
} else {
    Write-Host "Python-Installer bereits vorhanden: $pyDest"
}

Write-Host "Lade Python-Wheels (flask, flask-cors, Abhaengigkeiten) ..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python auf Build-PC nicht gefunden (zum Wheel-Download)." }

# Alte Wheels leeren und frisch holen (Windows amd64 / py3)
Get-ChildItem -Path $Wheels -File -ErrorAction SilentlyContinue | Remove-Item -Force
& $py.Source -m pip download `
    -r $Req `
    -d $Wheels `
    --only-binary=:all: `
    --python-version 312 `
    --platform win_amd64 `
    --implementation cp `
    --abi cp312
if ($LASTEXITCODE -ne 0) {
    Write-Host "Strict binary download fehlgeschlagen - versuche Standard-Download ..."
    & $py.Source -m pip download -r $Req -d $Wheels
    if ($LASTEXITCODE -ne 0) { throw "pip download fehlgeschlagen" }
}

$cfDest = Join-Path $Offline "cloudflared.exe"
if (-not (Test-Path $cfDest) -or (Get-Item $cfDest).Length -lt 1MB) {
    Write-Host "Lade cloudflared.exe (optional, fuer Online-Tunnel) ..."
    try {
        Invoke-WebRequest -Uri $CfUrl -OutFile $cfDest -UseBasicParsing
    } catch {
        Write-Warning "cloudflared Download fehlgeschlagen: $_"
    }
} else {
    Write-Host "cloudflared.exe bereits vorhanden"
}

$readme = @"
Gastro-System Offline-Bundle (wird in setup.exe eingebettet)
- $PyExeName : Python-Vollinstaller inkl. Tcl/Tk (Control Panel)
- wheels\    : Flask + Abhaengigkeiten fuer pip --no-index
- cloudflared.exe : optional fuer Cloudflare-Tunnel ohne Internet-Download
Erzeugt mit fetch-offline-deps.ps1
"@
Set-Content -Path (Join-Path $Offline "README.txt") -Value $readme -Encoding ASCII

Write-Host ""
Write-Host "Fertig: $Offline"
Get-ChildItem $Offline -Recurse -File | Select-Object FullName, Length | Format-Table -AutoSize
