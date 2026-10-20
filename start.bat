@echo off
cd /d "%~dp0"

start "UpFront Server" cmd /k "echo.| python cardserver.py"
timeout /t 2 /nobreak >nul
start "UpFront Client 1" python cardgame.py
timeout /t 1 /nobreak >nul
start "UpFront Client 2" python cardgame.py