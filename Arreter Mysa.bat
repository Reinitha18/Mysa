@echo off
rem Arrete le hub, sans effacer la base ni les modeles.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-stop.ps1" 
echo.
pause
