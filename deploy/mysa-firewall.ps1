# Ouvre les ports du hub Mysa dans le pare-feu Windows : 8000/TCP (dashboard + caméra, HTTPS) et
# 8883/TCP (MQTT TLS des ESP32), sur le profil « Privé » seulement. À lancer une fois, en administrateur :
# double-clic sur "Ouvrir pare-feu Mysa.bat" (la fenêtre demande l'élévation toute seule).
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "== Mysa : pare-feu Windows ==" -ForegroundColor Cyan
foreach ($rule in @(@{ Name = "Mysa HTTPS 8000"; Port = 8000 }, @{ Name = "Mysa MQTT 8883"; Port = 8883 })) {
    if (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue) {
        Write-Host "  [OK] règle « $($rule.Name) » déjà présente"
    } else {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Protocol TCP -LocalPort $rule.Port `
            -Action Allow -Profile Private | Out-Null
        Write-Host "  [OK] règle « $($rule.Name) » créée" -ForegroundColor Green
    }
}

# Les règles ne valent que sur un réseau « Privé » : un réseau « Public » bloquerait encore les nœuds.
$hubIp = $null
if (Test-Path ".env") {
    $line = Get-Content ".env" -Encoding UTF8 | Where-Object { $_ -match '^\s*MYSA_HUB_IP\s*=' } | Select-Object -First 1
    if ($line) { $hubIp = ($line -split '=', 2)[1].Trim() }
}
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -eq $hubIp } | Select-Object -First 1
if ($ip) {
    $netProfile = Get-NetConnectionProfile -InterfaceIndex $ip.InterfaceIndex -ErrorAction SilentlyContinue
    if ($netProfile -and $netProfile.NetworkCategory -eq "Public") {
        Write-Host "  Le réseau « $($netProfile.Name) » (IP $hubIp) est classé Public : les ports resteraient fermés." -ForegroundColor Yellow
        $ans = Read-Host "  Le passer en Privé (réseau de la maison, de confiance) ? (o/N)"
        if ($ans -match '^(o|O|y|Y)') {
            Set-NetConnectionProfile -InterfaceIndex $ip.InterfaceIndex -NetworkCategory Private
            Write-Host "  [OK] réseau passé en Privé" -ForegroundColor Green
        }
    } elseif ($netProfile) {
        Write-Host "  [OK] réseau « $($netProfile.Name) » classé $($netProfile.NetworkCategory)"
    }
} else {
    Write-Host "  MYSA_HUB_IP ($hubIp) introuvable sur ce PC : vérifiez .env." -ForegroundColor Yellow
}
Read-Host "Terminé. Entrée pour fermer"
