param(
    [string]$InstallRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$LanIp = "",
    [switch]$DisableCloudflare,
    [switch]$EnableCloudflare,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Continue"
$configPath = Join-Path $InstallRoot "gastro-host\config.cmd"
$bp = 8000
$fp = 8081

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-LanCandidates {
    $list = @()
    $addrs = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.IPAddress -notlike "192.168.56.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        })

    foreach ($c in $addrs) {
        $gw = Get-NetRoute -InterfaceIndex $c.InterfaceIndex -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
        $score = 0
        if ($gw) { $score += 100 }
        if ($c.InterfaceAlias -match "Wi-?Fi|WLAN|Ethernet|LAN") { $score += 10 }
        $gwIp = $null
        if ($gw) {
            $gwIp = ($gw | Select-Object -First 1).NextHop
        }
        $list += [PSCustomObject]@{
            IP      = $c.IPAddress
            Alias   = $c.InterfaceAlias
            Gateway = $gwIp
            Score   = $score
        }
    }
    return @($list | Sort-Object Score -Descending)
}

function Set-ConfigValue([string]$Path, [string]$Key, [string]$Value) {
    if (-not (Test-Path $Path)) {
        throw "config.cmd fehlt: $Path"
    }
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    $found = $false
    $pattern = '^\s*set\s+"' + [regex]::Escape($Key) + '=.*'
    $out = foreach ($line in $lines) {
        if ($line -match $pattern) {
            $found = $true
            "set `"$Key=$Value`""
        } else {
            $line
        }
    }
    if (-not $found) {
        $out = @($out) + "set `"$Key=$Value`""
    }
    Set-Content -LiteralPath $Path -Value $out -Encoding ASCII
}

function Ensure-FirewallRule([string]$Name, [int]$Port) {
    try {
        $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
        if ($existing) {
            Set-NetFirewallRule -DisplayName $Name -Enabled True -ErrorAction Stop | Out-Null
            Write-Host ("Firewall OK: " + $Name + " Port " + $Port)
            return $true
        }
        New-NetFirewallRule `
            -DisplayName $Name `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $Port `
            -Profile Any `
            -Description "Gastro-System LAN" -ErrorAction Stop | Out-Null
        Write-Host ("Firewall neu: " + $Name + " Port " + $Port)
        return $true
    } catch {
        Write-Warning ("Firewall Fehler: " + $_.Exception.Message)
        return $false
    }
}

function Test-ValidIpv4([string]$ip) {
    return $ip -match '^\d{1,3}(\.\d{1,3}){3}$'
}

Write-Host "=== Gastro LAN-Vorbereitung ==="
Write-Host ("InstallRoot: " + $InstallRoot)
Write-Host ("Admin: " + (Test-IsAdmin))
Write-Host ""
Write-Host "Hinweis: Die Router-IP (Fritzbox) braucht Gastro NICHT."
Write-Host "Wichtig ist nur die IP DIESES PCs, unter der Tablets ihn erreichen."
Write-Host ""

$candidates = Get-LanCandidates
$chosen = $null

if ($LanIp -and (Test-ValidIpv4 $LanIp)) {
    $chosen = $LanIp.Trim()
    Write-Host ("Manuelle IP (-LanIp): " + $chosen)
} elseif ($candidates.Count -eq 0) {
    Write-Warning "Keine LAN-IPv4 gefunden."
    if (-not $NonInteractive) {
        $manual = Read-Host "IP dieses PCs eingeben (z.B. 192.168.178.20) oder Enter fuer Abbruch"
        if ($manual -and (Test-ValidIpv4 $manual.Trim())) {
            $chosen = $manual.Trim()
        }
    }
    if (-not $chosen) {
        Write-Host "Abbruch. Netzwerkkabel/WLAN verbinden und erneut starten."
        exit 1
    }
} elseif ($candidates.Count -eq 1 -or $NonInteractive) {
    $chosen = $candidates[0].IP
    Write-Host ("Automatisch gewaehlt: " + $chosen + "  (" + $candidates[0].Alias + ")")
    if ($candidates[0].Gateway) {
        Write-Host ("  Gateway/Router erkannt: " + $candidates[0].Gateway + " (nur Info)")
    }
} else {
    Write-Host "Mehrere Netze gefunden - bitte das aktive Gastro-WLAN/LAN waehlen:"
    Write-Host ""
    $i = 1
    foreach ($c in $candidates) {
        $gwTxt = if ($c.Gateway) { "  Router/Gateway: " + $c.Gateway } else { "  (kein Gateway)" }
        Write-Host ("  [" + $i + "] " + $c.IP + "  " + $c.Alias + $gwTxt)
        $i++
    }
    Write-Host ("  [0] Andere IP manuell eingeben")
    Write-Host ""
    if ($NonInteractive) {
        $chosen = $candidates[0].IP
    } else {
        $sel = Read-Host ("Nummer 1-" + $candidates.Count + " (Enter = 1)")
        if ([string]::IsNullOrWhiteSpace($sel)) { $sel = "1" }
        if ($sel -eq "0") {
            $manual = Read-Host "IP dieses PCs"
            if ($manual -and (Test-ValidIpv4 $manual.Trim())) {
                $chosen = $manual.Trim()
            }
        } else {
            $idx = 0
            [void][int]::TryParse($sel, [ref]$idx)
            if ($idx -ge 1 -and $idx -le $candidates.Count) {
                $chosen = $candidates[$idx - 1].IP
            } else {
                $chosen = $candidates[0].IP
                Write-Warning ("Ungueltige Auswahl - nehme " + $chosen)
            }
        }
    }
}

if (-not $chosen) {
    Write-Host "Keine IP gesetzt - Abbruch."
    exit 1
}

Set-ConfigValue $configPath "GASTRO_LAN_IP" $chosen
Write-Host ("config.cmd: GASTRO_LAN_IP=" + $chosen)

if ($DisableCloudflare) {
    Set-ConfigValue $configPath "GASTRO_CLOUDFLARED_ENABLED" "0"
    Write-Host "Cloudflare Autostart: DEAKTIVIERT (Offline-Modus)"
} elseif ($EnableCloudflare) {
    Set-ConfigValue $configPath "GASTRO_CLOUDFLARED_ENABLED" "1"
    Write-Host "Cloudflare Autostart: AKTIVIERT"
}

$fwOk = $true
if (Test-IsAdmin) {
    $a = Ensure-FirewallRule "Gastro-System Backend API" $bp
    $b = Ensure-FirewallRule "Gastro-System Frontend UI" $fp
    $fwOk = $a -and $b
} else {
    Write-Warning "Kein Admin - Firewall-Regeln nicht gesetzt."
    Write-Host "Als Administrator ausfuehren: gastro-host\prepare-lan.cmd"
    Write-Host ("Oder manuell Ports " + $bp + " und " + $fp + " eingehend erlauben.")
    $fwOk = $false
}

Write-Host ""
Write-Host "Tablet-/Handy-URLs (gleiches WLAN, kein Gast-Netz):"
Write-Host ("  Frontend: http://" + $chosen + ":" + $fp + "/")
Write-Host ("  Backend:  http://" + $chosen + ":" + $bp + "/health")
Write-Host ""
Write-Host "Bei Netzwechsel (Heim -> Fritzbox Event): prepare-lan erneut ausfuehren."
Write-Host "Control Panel: nur Gastro-System starten. QR im Admin ueber diese LAN-URL."
if ($fwOk) {
    Write-Host "Fertig."
    exit 0
}
Write-Host "LAN-IP gesetzt. Firewall bitte noch als Admin setzen."
exit 2
