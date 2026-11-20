#Requires -RunAsAdministrator
param(
    [string]$InstallRoot = "",
    [switch]$KeepData,
    [switch]$Quiet,
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$AppName = "Gastro-System"
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue

function Get-InstallRootFromConfig {
    $cfg = Join-Path $PSScriptRoot "config.cmd"
    if (-not (Test-Path $cfg)) { return $null }
    foreach ($line in Get-Content $cfg -ErrorAction SilentlyContinue) {
        if ($line -match '^\s*set\s+"GASTRO_ROOT=(.+)"\s*$') {
            return $Matches[1]
        }
    }
    return $null
}

if (-not $InstallRoot) {
    $InstallRoot = Get-InstallRootFromConfig
}
if (-not $InstallRoot) {
    $InstallRoot = Split-Path $PSScriptRoot -Parent
}

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
Write-Host ("Deinstalliere " + $AppName)
Write-Host ("Ordner: " + $InstallRoot)

if (-not $Quiet -and -not $Force) {
    $msg = "Gastro-System wirklich deinstallieren?`r`n`r`nOrdner: $InstallRoot`r`n`r`nPython 3.12 bleibt auf dem PC."
    $r = [System.Windows.Forms.MessageBox]::Show(
        $msg,
        ($AppName + " deinstallieren"),
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    )
    if ($r -ne [System.Windows.Forms.DialogResult]::Yes) {
        Write-Host "Abgebrochen."
        exit 1
    }
}

$hostDir = Join-Path $InstallRoot "gastro-host"
foreach ($script in @("stop-backend.cmd", "stop-frontend.cmd", "stop-cloudflared.cmd")) {
    $p = Join-Path $hostDir $script
    if (Test-Path $p) {
        Write-Host ("Stoppe: " + $script)
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$p`"" -Wait -WindowStyle Hidden
    }
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @("python.exe", "pythonw.exe") -and
        $_.CommandLine -and
        ($_.CommandLine -like ("*" + $InstallRoot.Replace("\", "\\") + "*") -or $_.CommandLine -like ("*" + $InstallRoot + "*"))
    } |
    ForEach-Object {
        Write-Host ("Beende PID " + $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

foreach ($tn in @("GastroBackend", "GastroFrontend", "GastroCloudflared")) {
    schtasks.exe /Delete /TN $tn /F 2>$null | Out-Null
    Write-Host ("Task entfernt: " + $tn)
}

foreach ($desk in @(
        (Join-Path $env:USERPROFILE "Desktop"),
        (Join-Path $env:USERPROFILE "Schreibtisch"),
        (Join-Path $env:PUBLIC "Desktop")
    )) {
    foreach ($name in @("Gastro-System.lnk", "Gastro deinstallieren.lnk", "Gastro-System deinstallieren.lnk")) {
        $lnk = Join-Path $desk $name
        if (Test-Path $lnk) {
            Remove-Item $lnk -Force -ErrorAction SilentlyContinue
            Write-Host ("Verknuepfung entfernt: " + $lnk)
        }
    }
}

$unKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\GastroSystem"
if (Test-Path $unKey) {
    Remove-Item $unKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Uninstall-Registry entfernt"
}

if (Test-Path $InstallRoot) {
    if ($KeepData) {
        $data = Join-Path $InstallRoot "data"
        $backup = Join-Path (Split-Path $InstallRoot -Parent) ("Gastro-System-Daten-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        if (Test-Path $data) {
            Copy-Item $data $backup -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host ("Datenkopie: " + $backup)
        }
    }
    Write-Host ("Loesche Ordner: " + $InstallRoot)
    try {
        Remove-Item -LiteralPath $InstallRoot -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Warning ("Ordner belegt, spaeteres Loeschen: " + $_.Exception.Message)
        $bat = Join-Path $env:TEMP "gastro-uninstall-finish.cmd"
        $lines = @(
            "@echo off",
            "timeout /t 2 /nobreak >nul",
            ("rd /s /q """ + $InstallRoot + """"),
            "del /f /q ""%~f0"""
        )
        [System.IO.File]::WriteAllLines($bat, $lines)
        Start-Process -FilePath $bat -WindowStyle Hidden
    }
}

Write-Host ""
Write-Host "Deinstallation abgeschlossen."
if (-not $Quiet) {
    [System.Windows.Forms.MessageBox]::Show(
        "Gastro-System wurde deinstalliert.",
        $AppName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}
exit 0
