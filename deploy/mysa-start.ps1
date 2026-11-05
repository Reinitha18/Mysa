# Démarre le hub Mysa (broker + moteur + API/dashboard/caméra) en une fois.
# Double-clic sur "Demarrer Mysa.bat" à la racine, ou : powershell -ExecutionPolicy Bypass -File deploy\mysa-start.ps1
# Prépare automatiquement : les certificats (refaits si l'IP du PC change) et les comptes du broker
# (resynchronisés avec .env à chaque démarrage). Voir docs/deploiement_windows.md.

# "Continue" et non "Stop" : sous PowerShell 5.1, "Stop" transforme en erreur fatale tout ce que docker
# écrit sur stderr, même les messages normaux ("Unable to find image ... locally", avertissements).
# Chaque commande docker est donc vérifiée par son code de retour ($LASTEXITCODE).
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop   # racine du dépôt

function Read-DotEnv([string]$path) {
    $map = @{}
    if (Test-Path $path) {
        foreach ($line in Get-Content $path -Encoding UTF8) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
                $map[$matches[1]] = $matches[2].Trim().Trim('"', "'")
            }
        }
    }
    return $map
}

function Get-Sha256([string]$text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLower()
}

Write-Host "== Mysa : démarrage du hub ==" -ForegroundColor Cyan

# 1) Docker en marche ?
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Commande docker introuvable. Installez Docker Desktop." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop ne répond pas. Lancez-le, attendez « Engine running », puis réessayez." }

# 2) Fichier .env
# Le Bloc-notes enregistre souvent ".env" sous le nom ".env.txt" : on le signale.
if (-not (Test-Path ".env") -and (Test-Path ".env.txt")) {
    throw "Le fichier s'appelle .env.txt : renommez-le en .env (sans .txt) puis relancez."
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env" -ErrorAction Stop
    Write-Host "  .env créé depuis .env.example." -ForegroundColor Yellow
    Write-Host "  Renseignez MYSA_HUB_IP (IP de ce PC), le Wi-Fi et les mots de passe dans .env, puis relancez." -ForegroundColor Yellow
    exit 1
}
$env_ = Read-DotEnv ".env"
$hubIp = $env_.MYSA_HUB_IP
if (-not $hubIp) { throw "MYSA_HUB_IP manque dans .env (IP de ce PC sur le réseau des nœuds)." }
Write-Host "  .env lu : $((Resolve-Path '.env').Path) - IP du hub : $hubIp"

# L'IP doit être celle de ce PC, sinon ni les ESP32 ni le téléphone ne trouveront le hub.
$localIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress })
if ($localIps.Count -gt 0 -and $localIps -notcontains $hubIp) {
    Write-Host "  ATTENTION : $hubIp n'est pas une adresse de ce PC ($($localIps -join ', '))." -ForegroundColor Yellow
    Write-Host "  Corrigez MYSA_HUB_IP dans .env (ipconfig), relancez, puis retéléversez les nœuds." -ForegroundColor Yellow
}

$accounts = [ordered]@{
    "mysa-engine"  = $env_.MQTT_PASSWORD
    "mysa-cam"     = $env_.MYSA_CAM_PASSWORD
    "esp32-sec-01" = $env_.MYSA_SEC_PASSWORD
    "esp32-cmf-01" = $env_.MYSA_CMF_PASSWORD
}
foreach ($name in $accounts.Keys) {
    $pw = $accounts[$name]
    if (-not $pw) { throw "Mot de passe du compte $name vide dans .env." }
    if ($pw -match "['\s`"]") { throw "Le mot de passe du compte $name contient une apostrophe, un guillemet ou un espace : choisissez lettres, chiffres, - et _." }
    if ($pw -eq "change-me") { Write-Host "  ATTENTION : le compte $name a encore le mot de passe « change-me »." -ForegroundColor Yellow }
}
if (-not $env_.MYSA_DASHBOARD_PASSWORD) {
    Write-Host "  ATTENTION : MYSA_DASHBOARD_PASSWORD est vide : le dashboard (serrure, alarme) est ouvert à tout le réseau." -ForegroundColor Yellow
}

# 3) Certificats (CA Mysa + certificat serveur mysa-hub). La CA existante est toujours réutilisée :
# seul server.crt est refait (absent, ou IP du hub changée), sans changer le CA des nœuds.
$certsChanged = $false
if (Test-Path "broker/certs/server.crt") {
    $san = docker run --rm -v "${PWD}/broker/certs:/c" alpine:3.20 sh -c `
        "apk add -q --no-cache openssl >/dev/null 2>&1 && openssl x509 -in /c/server.crt -noout -ext subjectAltName"
    if ($LASTEXITCODE -eq 0 -and ($san -join ' ') -notmatch "DNS:$([regex]::Escape($hubIp))(,|\s|$)") {
        Write-Host "  Le certificat du hub ne couvre pas $hubIp (IP changée) : il va être refait." -ForegroundColor Yellow
        Remove-Item "broker/certs/server.crt", "broker/certs/server.key" -ErrorAction SilentlyContinue
    }
}
if (-not (Test-Path "broker/certs/server.crt")) {
    $certsChanged = $true
    Write-Host "  Génération des certificats (CA + mysa-hub, IP $hubIp)..." -ForegroundColor Cyan
    docker run --rm -v "${PWD}:/app" -w /app alpine:3.20 `
        sh -c "apk add --no-cache openssl bash >/dev/null && bash scripts/gen_certs.sh $hubIp mysa-hub"
    if ($LASTEXITCODE -ne 0) { throw "Échec de la génération des certificats." }
} else {
    Write-Host "  Certificats présents et valables pour $hubIp (broker/certs)."
}

# 4) Comptes du broker : recréés dès que les mots de passe de .env changent (empreinte dans passwd.sha256).
$fingerprint = Get-Sha256 (($accounts.Keys | ForEach-Object { "$_=$($accounts[$_])" }) -join "`n")
$passwdChanged = $false
$known = if (Test-Path "broker/passwd.sha256") { (Get-Content "broker/passwd.sha256" -Raw).Trim() } else { "" }
if (-not (Test-Path "broker/passwd") -or $known -ne $fingerprint) {
    $passwdChanged = $true
    Write-Host "  Création des comptes du broker ($($accounts.Keys -join ', '))..." -ForegroundColor Cyan
    $cmds = @()
    $first = $true
    foreach ($name in $accounts.Keys) {
        $flag = if ($first) { "-c " } else { "" }
        $cmds += "mosquitto_passwd -b $flag/b/passwd $name '$($accounts[$name])'"
        $first = $false
    }
    $cmds += "chmod 644 /b/passwd"
    docker run --rm -v "${PWD}/broker:/b" eclipse-mosquitto:2 sh -c ($cmds -join " && ")
    if ($LASTEXITCODE -ne 0) { throw "Échec de la génération du fichier de mots de passe du broker." }
    Set-Content -Path "broker/passwd.sha256" -Value $fingerprint -NoNewline
} else {
    Write-Host "  Comptes du broker à jour (broker/passwd)."
}

# 5) Démarrage. Mosquitto et uvicorn ne relisent certificats et comptes qu'au démarrage : on les
# redémarre si l'un d'eux vient de changer.
Write-Host "  Construction et lancement des conteneurs (long la première fois)..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "Échec du lancement des conteneurs (voir les messages ci-dessus)." }
if ($certsChanged) { docker compose restart broker api engine }
elseif ($passwdChanged) { docker compose restart broker }

# 6) Pare-feu : sans les règles, ni les ESP32 ni le téléphone ne joignent le hub.
$rules = @(Get-NetFirewallRule -DisplayName "Mysa *" -ErrorAction SilentlyContinue)
if ($rules.Count -lt 2) {
    Write-Host "  ATTENTION : règles de pare-feu Mysa absentes : lancez « Ouvrir pare-feu Mysa.bat » (administrateur)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "== Hub Mysa démarré ==" -ForegroundColor Green
Write-Host "  Dashboard : https://$hubIp`:8000/dashboard/   (mot de passe : MYSA_DASHBOARD_PASSWORD dans .env)"
Write-Host "  Caméra    : https://$hubIp`:8000/camera/   (depuis le téléphone, après connexion au dashboard)"
Write-Host "  Broker    : $hubIp`:8883 (TLS)"
if ($certsChanged) {
    Write-Host "  Certificats refaits : retéléversez les deux nœuds (Televerser sec01.bat / Televerser cmf01.bat)." -ForegroundColor Yellow
}
Write-Host "  Vérifier tout : « Verifier Mysa.bat »   |   Journaux : docker compose logs -f   |   Arrêt : « Arreter Mysa.bat »"
