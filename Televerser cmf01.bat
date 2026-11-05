@echo off
rem Televerse le noeud confort (DHT22, relais) puis ouvre son moniteur.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-flash.ps1" -Node cmf01
echo.
pause
