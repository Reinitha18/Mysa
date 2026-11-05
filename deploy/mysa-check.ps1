# Vérifie tout le déploiement Mysa en une fois (à lancer avant la soutenance) :
# Docker, services, IP, certificats, TLS, pare-feu, nœuds connectés, notifications.
# Double-clic sur "Verifier Mysa.bat", ou : powershell -ExecutionPolicy Bypass -File deploy\mysa-check.ps1
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop

$problems = 0
function Ok([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Bad([string]$msg, [string]$fix) {
    Write-Host "  [!!] $msg" -ForegroundColor Red
    if ($fix) { Write-Host "       -> $fix" -ForegroundColor Yellow }
    $script:problems++
}

function Read-DotEnv([string]$path) {
    $map = @{}
    foreach ($line in Get-Content $path -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $map[$matches[1]] = $matches[2].Trim().Trim('"', "'") }
    }
    return $map
}

Write-Host "== Mysa : vérification du déploiement ==" -ForegroundColor Cyan

# --- .env
if (-not (Test-Path ".env")) { Bad ".env absent" "copier .env.example en .env et le remplir"; exit 1 }
$e = Read-DotEnv ".env"
$hubIp = $e.MYSA_HUB_IP
$localIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress })
if ($localIps -contains $hubIp) { Ok "MYSA_HUB_IP = $hubIp est bien l'adresse de ce PC" }
else { Bad "MYSA_HUB_IP = $hubIp n'est pas une adresse de ce PC ($($localIps -join ', '))" "corriger .env, relancer Demarrer Mysa.bat puis retéléverser les nœuds" }
foreach ($k in "MYSA_WIFI_SSID", "MYSA_WIFI_PASS", "MQTT_PASSWORD", "MYSA_CAM_PASSWORD", "MYSA_SEC_PASSWORD", "MYSA_CMF_PASSWORD", "MYSA_DASHBOARD_PASSWORD") {
    if (-not $e[$k]) { Bad "$k vide dans .env" "le renseigner" }
    elseif ($e[$k] -eq "change-me") { Bad "$k vaut encore « change-me »" "choisir un vrai mot de passe" }
}

# --- Docker et services
docker info *> $null
if ($LASTEXITCODE -ne 0) { Bad "Docker Desktop ne répond pas" "lancer Docker Desktop"; exit 1 }
Ok "Docker Desktop en marche"
$running = @(docker compose ps --services --filter status=running 2>$null)
foreach ($svc in "broker", "engine", "api") {
    if ($running -contains $svc) { Ok "service $svc en marche" }
    else { Bad "service $svc arrêté" "Demarrer Mysa.bat, puis : docker compose logs $svc" }
}

# --- Certificats et TLS (vus comme un ESP32 les voit)
if (Test-Path "broker/certs/ca.crt") {
    $out = docker run --rm -v "${PWD}/broker/certs:/c" alpine:3.20 sh -c (
        "apk add -q --no-cache openssl >/dev/null 2>&1; " +
        "openssl verify -CAfile /c/ca.crt /c/server.crt; " +
        "openssl x509 -in /c/server.crt -noout -ext subjectAltName -enddate; " +
        "echo | openssl s_client -connect ${hubIp}:8883 -CAfile /c/ca.crt 2>/dev/null | grep 'Verify return code'; " +
        "echo | openssl s_client -connect ${hubIp}:8000 -CAfile /c/ca.crt 2>/dev/null | grep 'Verify return code'")
    $text = $out -join "`n"
    if ($text -match "server.crt: OK") { Ok "server.crt signé par ca.crt" } else { Bad "server.crt n'est pas signé par ca.crt" "supprimer broker\certs puis relancer Demarrer Mysa.bat et retéléverser les nœuds" }
    if ($text -match "DNS:$([regex]::Escape($hubIp))") { Ok "certificat valable pour $hubIp" } else { Bad "le certificat ne couvre pas $hubIp" "relancer Demarrer Mysa.bat (il le refait)" }
    $codes = @([regex]::Matches($text, "Verify return code: (\d+)") | ForEach-Object { $_.Groups[1].Value })
    if ($codes.Count -ge 1 -and $codes[0] -eq "0") { Ok "broker MQTT TLS joignable sur ${hubIp}:8883" } else { Bad "broker TLS injoignable ou certificat refusé sur ${hubIp}:8883" "docker compose restart broker ; vérifier le pare-feu" }
    if ($codes.Count -ge 2 -and $codes[1] -eq "0") { Ok "dashboard HTTPS joignable sur ${hubIp}:8000" } else { Bad "dashboard HTTPS injoignable sur ${hubIp}:8000" "docker compose logs api" }
} else {
    Bad "broker\certs\ca.crt absent" "lancer Demarrer Mysa.bat"
}

# --- Pare-feu
$rules = @(Get-NetFirewallRule -DisplayName "Mysa *" -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq "True" })
if ($rules.Count -ge 2) { Ok "pare-feu : ports 8000 et 8883 ouverts" } else { Bad "règles de pare-feu Mysa absentes" "Ouvrir pare-feu Mysa.bat (administrateur)" }
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -eq $hubIp } | Select-Object -First 1
if ($ip) {
    $netProfile = Get-NetConnectionProfile -InterfaceIndex $ip.InterfaceIndex -ErrorAction SilentlyContinue
    if ($netProfile.NetworkCategory -eq "Public") { Bad "réseau « $($netProfile.Name) » classé Public : les ports restent fermés" "Ouvrir pare-feu Mysa.bat le passe en Privé" }
}

# --- Nœuds et caméra : dernières connexions vues par le broker (30 dernières minutes)
$logs = (docker compose logs broker --since 30m 2>&1) -join "`n"
foreach ($node in "esp32-sec-01", "esp32-cmf-01") {
    $connected = [regex]::Matches($logs, "connected from [^\n]* as $node").Count
    $refused = [regex]::Matches($logs, "(not authorised|bad user name or password)[^\n]*$node|$node[^\n]*(not authorised|bad user name or password)").Count
    if ($connected -gt 0) { Ok "nœud $node connecté au broker" }
    elseif ($refused -gt 0) { Bad "nœud $node refusé (mot de passe)" "retéléverser le nœud après avoir corrigé .env" }
    else { Bad "nœud $node pas vu depuis 30 min" "alimenter la carte ; moniteur série : Televerser $($node.Replace('esp32-','').Replace('-','')).bat" }
}

# --- Notifications
$channels = @()
if ($e.MYSA_SMTP_HOST -and $e.MYSA_SMTP_USER -and $e.MYSA_SMTP_PASSWORD -and $e.MYSA_SMTP_TO) { $channels += "e-mail" }
if ($e.MYSA_SMS_URL -and $e.MYSA_SMS_TO) { $channels += "SMS" }
if ($e.MYSA_NOTIFY -eq "0") { Bad "notifications coupées (MYSA_NOTIFY=0)" "" }
elseif ($channels.Count -gt 0) { Ok "notifications configurées : $($channels -join ', ') (tester depuis le dashboard, page Moteur)" }
else { Bad "aucun canal de notification configuré" "renseigner un canal dans .env (docs/notifications.md), puis Demarrer Mysa.bat" }

Write-Host ""
if ($problems -eq 0) { Write-Host "== Tout est prêt. Dashboard : https://$hubIp`:8000/dashboard/ ==" -ForegroundColor Green }
else { Write-Host "== $problems point(s) à corriger (voir les flèches ci-dessus) ==" -ForegroundColor Yellow }
