# Arrête le hub Mysa (conteneurs), sans supprimer la base ni les modèles appris.
# Double-clic, ou : powershell -File deploy\mysa-stop.ps1
# "Continue" : sous PowerShell 5.1, "Stop" rendrait fatal le moindre message de docker sur stderr.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop

Write-Host "== Mysa : arrêt du hub ==" -ForegroundColor Cyan
docker compose down
Write-Host "Hub arrêté. La base et les modèles sont conservés (volumes Docker)." -ForegroundColor Green
Write-Host "Pour tout redémarrer : deploy\mysa-start.ps1"
