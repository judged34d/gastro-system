# Wrapper: Offline-Frischinstallations-Checks vor setup.exe-Build.
$ErrorActionPreference = 'Stop'
$InstallerDir = $PSScriptRoot
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw 'Python auf Build-PC nicht gefunden' }
& $py.Source (Join-Path $InstallerDir 'verify_offline_install.py')
exit $LASTEXITCODE
