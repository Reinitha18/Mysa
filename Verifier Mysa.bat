@echo off
rem Verifie tout le deploiement avant la soutenance.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-check.ps1" 
echo.
pause
