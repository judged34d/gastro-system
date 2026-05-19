# Optional: einmal als Administrator – Windows-Tasks für Autostart.
param(
    [string]$InstallRoot = 'C:\Applikationen\Gastro-System',
    [switch]$CloudflareEnabled
)

$ErrorActionPreference = 'Stop'
$hostDir = Join-Path $InstallRoot 'gastro-host'
$dbPath = Join-Path $InstallRoot 'data\database.db'
$runAs = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $hostDir)) {
    throw "gastro-host nicht gefunden: $hostDir"
}

[Environment]::SetEnvironmentVariable('GASTRO_DB_PATH', $dbPath, 'User')
try {
    [Environment]::SetEnvironmentVariable('GASTRO_DB_PATH', $dbPath, 'Machine')
} catch {
    Write-Warning "Machine-GASTRO_DB_PATH: Admin noetig."
}

$cmds = @{
    GastroBackend  = Join-Path $hostDir 'run-backend.cmd'
    GastroFrontend = Join-Path $hostDir 'run-frontend.cmd'
}
if ($CloudflareEnabled) {
    $cmds['GastroCloudflared'] = Join-Path $hostDir 'run-cloudflared.cmd'
} else {
    schtasks.exe /Delete /TN GastroCloudflared /F 2>$null | Out-Null
}

foreach ($pair in $cmds.GetEnumerator()) {
    $tr = '"' + $pair.Value + '"'
    schtasks.exe /Create /TN $pair.Key /TR $tr /SC ONLOGON /RU $runAs /RL HIGHEST /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "schtasks $($pair.Key) fehlgeschlagen" }
    Write-Host "Task: $($pair.Key) -> $($pair.Value)"
}
Write-Host "Fertig. InstallRoot=$InstallRoot Cloudflare=$CloudflareEnabled"
