# Compile et téléverse le firmware d'un nœud ESP32, puis ouvre son moniteur série.
# Double-clic sur "Televerser sec01.bat" / "Televerser cmf01.bat", ou :
#   powershell -ExecutionPolicy Bypass -File deploy\mysa-flash.ps1 -Node sec01 [-Port COM3] [-NoMonitor]
# La configuration du nœud (Wi-Fi, IP du hub, mot de passe MQTT, CA) est lue dans .env et
# broker/certs/ca.crt à la compilation (firmware/scripts/gen_config.py) : rien à recopier.
param(
    [Parameter(Mandatory = $true)][ValidateSet("sec01", "cmf01", "hwtest_sec", "hwtest_cmf")][string]$Node,
    [string]$Port,
    [switch]$NoMonitor
)
$ErrorActionPreference = "Continue"   # voir mysa-start.ps1 : codes de retour vérifiés un par un
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop

$labels = @{ sec01 = "sécurité (PIR, RFID, serrure)"; cmf01 = "confort (DHT22, relais)";
             hwtest_sec = "test matériel de sec-01"; hwtest_cmf = "test matériel de cmf-01" }
Write-Host "== Mysa : téléversement du nœud $Node - $($labels[$Node]) ==" -ForegroundColor Cyan

# PlatformIO : celui de l'extension VS Code, sinon celui du PATH.
$pio = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\pio.exe"
if (-not (Test-Path $pio)) {
    $cmd = Get-Command pio -ErrorAction SilentlyContinue
    if ($cmd) { $pio = $cmd.Source }
    else { throw "PlatformIO introuvable : installez VS Code + l'extension PlatformIO IDE, ouvrez-la une fois, puis relancez." }
}

if ($Node -in @("sec01", "cmf01") -and -not (Test-Path "broker/certs/ca.crt")) {
    throw "broker\certs\ca.crt absent : démarrez d'abord le hub (« Demarrer Mysa.bat »), qui crée les certificats."
}

if (-not $Port) {
    Write-Host "  Ports série détectés :"
    & $pio device list --serial
    $Port = Read-Host "  Port COM de la carte $Node (ex. COM3)"
    if (-not $Port) { throw "Aucun port indiqué." }
}
$Port = $Port.Trim().ToUpper()

Write-Host "  Compilation + téléversement sur $Port (la 1re fois, PlatformIO télécharge ses outils)..." -ForegroundColor Cyan
Write-Host "  Si « Connecting....___ » s'éternise : maintenir le bouton BOOT de la carte." -ForegroundColor DarkGray
& $pio run -d firmware -e $Node -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Téléversement échoué. Vérifiez le port ($Port), le câble USB (données), et maintenez BOOT pendant « Connecting »."
}
Write-Host "  Téléversement réussi." -ForegroundColor Green

if (-not $NoMonitor) {
    Write-Host "  Moniteur série (Ctrl+C pour quitter). Attendu : [MQTT] Connexion TLS a ... OK" -ForegroundColor Cyan
    & $pio device monitor -d firmware -e $Node -p $Port
}
