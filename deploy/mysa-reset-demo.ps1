# Réinitialise la base et les modèles appris AVANT une démonstration : repart d'un état propre.
# Double-clic, ou : powershell -File deploy\mysa-reset-demo.ps1
# Les certificats et les comptes du broker sont conservés.
# "Continue" : sous PowerShell 5.1, "Stop" rendrait fatal le moindre message de docker sur stderr.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop

Write-Host "== Mysa : remise à zéro de la démonstration ==" -ForegroundColor Cyan
$ans = Read-Host "Effacer la base et les modèles appris ? (o/N)"
if ($ans -notmatch '^(o|O|y|Y)') { Write-Host "Annulé."; exit }

docker compose down
# Les volumes nommés sont préfixés par le nom du projet (dossier) : on les retire par leur label.
docker volume ls -q --filter "label=com.docker.compose.project" |
    Where-Object { $_ -match 'mysa-(data|models)$' } |
    ForEach-Object { docker volume rm $_ | Out-Null }

Write-Host "  Base et modèles effacés. Redémarrage du hub..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "Hub réinitialisé et redémarré. Les appareils ré-apprendront leur comportement." -ForegroundColor Green
