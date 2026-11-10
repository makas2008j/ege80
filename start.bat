@echo off
cd /d "%~dp0"
where py >nul 2>&1 && py -m http.server 8080 || python -m http.server 8080