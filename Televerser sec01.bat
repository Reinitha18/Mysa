@echo off
rem Televerse le noeud securite (PIR, RFID, serrure) puis ouvre son moniteur.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\mysa-flash.ps1" -Node sec01
echo.
pause
