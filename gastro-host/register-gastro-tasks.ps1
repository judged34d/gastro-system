# Optional: einmal als Administrator – Windows-Tasks für Autostart (ohne sichtbares Konsolenfenster).
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

# Ensure hidden VBS wrappers exist
$wrappers = @{
    'run-backend-hidden.vbs'     = 'run-backend.cmd'
    'run-frontend-hidden.vbs'    = 'run-frontend.cmd'
    'run-cloudflared-hidden.vbs' = 'run-cloudflared.cmd'
}
foreach ($pair in $wrappers.GetEnumerator()) {
    $vbsPath = Join-Path $hostDir $pair.Key
    $cmdName = $pair.Value
    $content = @"
' Autostart without visible console window
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & sh.CurrentDirectory & "\$cmdName""", 0, False
"@
    Set-Content -Path $vbsPath -Value $content -Encoding ASCII
}

$cmds = @{
    GastroBackend  = Join-Path $hostDir 'run-backend-hidden.vbs'
    GastroFrontend = Join-Path $hostDir 'run-frontend-hidden.vbs'
}
if ($CloudflareEnabled) {
    $cmds['GastroCloudflared'] = Join-Path $hostDir 'run-cloudflared-hidden.vbs'
} else {
    schtasks.exe /Delete /TN GastroCloudflared /F 2>$null | Out-Null
}

foreach ($pair in $cmds.GetEnumerator()) {
    $tr = 'wscript.exe //B //Nologo "' + $pair.Value + '"'
    schtasks.exe /Create /TN $pair.Key /TR $tr /SC ONLOGON /RU $runAs /RL HIGHEST /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "schtasks $($pair.Key) fehlgeschlagen" }
    Write-Host "Task: $($pair.Key) -> $($pair.Value) (hidden)"
}
Write-Host "Fertig. InstallRoot=$InstallRoot Cloudflare=$CloudflareEnabled"
