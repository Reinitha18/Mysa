@echo off
rem Efface la base et les modeles appris (PAS juste avant la demo).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-reset-demo.ps1" 
echo.
pause
