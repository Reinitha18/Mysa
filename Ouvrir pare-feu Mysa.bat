@echo off
rem Ouvre les ports 8000 et 8883 (demande les droits administrateur).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-firewall.ps1" 
echo.
pause
