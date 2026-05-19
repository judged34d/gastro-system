# Optional: einmal als Administrator – nur Windows-Tasks, legt NICHTS unter C:\srv an.
$ErrorActionPreference = 'Stop'
$hostDir = 'C:\Applikationen\Gastro-System\gastro-host'
$dbPath = 'C:\Applikationen\Gastro-System\data\database.db'
$runAs = "$env:USERDOMAIN\$env:USERNAME"

[Environment]::SetEnvironmentVariable('GASTRO_DB_PATH', $dbPath, 'User')
try {
    [Environment]::SetEnvironmentVariable('GASTRO_DB_PATH', $dbPath, 'Machine')
} catch {
    Write-Warning "Machine-GASTRO_DB_PATH: Admin noetig."
}

$cmds = @{
    GastroBackend     = "$hostDir\run-backend.cmd"
    GastroFrontend    = "$hostDir\run-frontend.cmd"
    GastroCloudflared = "$hostDir\run-cloudflared.cmd"
}
foreach ($pair in $cmds.GetEnumerator()) {
    $tr = '"' + $pair.Value + '"'
    schtasks.exe /Create /TN $pair.Key /TR $tr /SC ONLOGON /RU $runAs /RL HIGHEST /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "schtasks $($pair.Key) fehlgeschlagen" }
    Write-Host "Task: $($pair.Key) -> $($pair.Value)"
}
Write-Host "Fertig. Kein C:\srv."
