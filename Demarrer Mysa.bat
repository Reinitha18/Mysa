@echo off
rem Demarre le hub (Docker Desktop doit etre lance).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-start.ps1" 
echo.
pause
