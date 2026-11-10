@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title EGE AI + Cloudflare Tunnel - START

echo ================================================
echo  EGE Russian 80+ - AI + Cloudflare Tunnel
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (echo ERROR: Python not found.&pause&exit /b 1)
where curl >nul 2>&1
if errorlevel 1 (echo ERROR: curl not found.&pause&exit /b 1)

REM -------- locate cloudflared (tunnel/) --------
set "CF=%~dp0tunnel\cloudflared.exe"
if not exist "%CF%" set "CF="
if not defined CF if exist "%~dp0cloudflared.exe" set "CF=%~dp0cloudflared.exe"
if not defined CF if exist "%LOCALAPPDATA%\cloudflared.exe" set "CF=%LOCALAPPDATA%\cloudflared.exe"
if defined CF goto :cf_ok
echo ERROR: cloudflared.exe not found. Put it in tunnel\ or install cloudflared.
exit /b 1
:cf_ok

REM -------- AI token (create once, reuse) --------
set "DATA_DIR=%~dp0data"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
set "TOKEN_FILE=%DATA_DIR%\ai_token.txt"
if not exist "%TOKEN_FILE%" (
  powershell -NoProfile -Command "$b=New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)" > "%TOKEN_FILE%"
)
set /p AI_TOKEN=<"%TOKEN_FILE%"

REM ---------- 1. Ollama ----------
echo [1/4] Checking Ollama...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo       Starting Ollama...
  start "Ollama" ollama serve
  set "OK="
  for /l %%I in (1,1,30) do if not defined OK (
    curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
    if not errorlevel 1 set "OK=1"
    if not defined OK timeout /t 1 /nobreak >nul
  )
)
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (echo ERROR: Ollama unavailable on port 11434.&pause&exit /b 1)
echo       Ollama ready.

REM ---------- 2. AI bridge (port 8000, token-protected) ----------
echo [2/4] Starting AI bridge on http://127.0.0.1:8000  (auth on)
set "BRIDGE_DIR="
if exist "%~dp0bridge" (set "BRIDGE_DIR=%~dp0bridge")
if not defined BRIDGE_DIR if exist "%~dp0ege_local_ai_bridge" (set "BRIDGE_DIR=%~dp0ege_local_ai_bridge")
if not defined BRIDGE_DIR (echo ERROR: bridge folder not found.&pause&exit /b 1)

start "EGE AI Bridge" /d "%BRIDGE_DIR%" cmd /k "set AI_TOKEN=%AI_TOKEN%&&set OLLAMA_MODEL=qwen2.5vl:7b&&python ai_bridge.py"

echo       Waiting for bridge...
set "BRIDGE_OK="
for /l %%I in (1,1,20) do if not defined BRIDGE_OK (
  curl -s -H "Authorization: Bearer %AI_TOKEN%" http://127.0.0.1:8000/api/ >nul 2>&1
  if not errorlevel 1 set "BRIDGE_OK=1"
  if not defined BRIDGE_OK timeout /t 1 /nobreak >nul
)
if not defined BRIDGE_OK (echo ERROR: AI bridge did not start.&pause&exit /b 1)
echo       Bridge ready.

REM ---------- 3. Cloudflare tunnel ----------
echo [3/4] Starting Cloudflare Tunnel -> 8000
set "TUNNEL_LOG=%DATA_DIR%\cloudflared_tunnel.log"
if exist "%TUNNEL_LOG%" del /q "%TUNNEL_LOG%" >nul 2>&1
start "CF Tunnel" /min "%CF%" tunnel --no-autoupdate --url http://127.0.0.1:8000 --logfile "%TUNNEL_LOG%"

echo       Waiting for public URL...
set "PUBLIC_URL="
for /l %%I in (1,1,35) do if not defined PUBLIC_URL (
  for /f "usebackq delims=" %%u in (`powershell -NoProfile -Command "$t=Get-Content -Raw '%TUNNEL_LOG%' -ErrorAction SilentlyContinue; if($t){ $m=[regex]::Match($t,'https://[a-z0-9-]+\.trycloudflare\.com'); if($m.Success){$m.Value}}" 2^>$null`) do set "PUBLIC_URL=%%u"
  if not defined PUBLIC_URL timeout /t 1 /nobreak >nul
)

echo.
echo ================================================
if defined PUBLIC_URL (
  echo  PHONE URL:   %PUBLIC_URL%
  echo  AI TOKEN:    %AI_TOKEN%
  echo.
  echo  On the phone: paste PHONE URL and AI TOKEN
  echo  into the AI field, then Save and Check.
) else (
  echo  PHONE URL:   NOT READY (check data\cloudflared_tunnel.log)
  echo  Local AI:    http://127.0.0.1:8000  (works on this PC)
)
echo  Token file:   %TOKEN_FILE%
echo ================================================
echo.

REM -------- write live AI config for the site pages --------
set "CFG_FILE=%~dp0site-config.js"
(
  echo window.SITE_AI = {
  echo   url: "%PUBLIC_URL%",
  echo   token: "%AI_TOKEN%"
  echo };
)> "%CFG_FILE%"
if exist "%CFG_FILE%" (echo [config] site-config.js updated.) else (echo WARNING: cannot write site-config.js)

REM ---------- 4. Local site server + open ----------
echo [4/4] Starting local site server on http://127.0.0.1:8080
start "EGE Site" cmd /k "cd /d "%~dp0" && python -m http.server 8080"
set "SITE_OK="
for /l %%I in (1,1,20) do if not defined SITE_OK (
  curl -s -o nul http://127.0.0.1:8080/ >nul 2>&1
  if not errorlevel 1 set "SITE_OK=1"
  if not defined SITE_OK timeout /t 1 /nobreak >nul
)
if defined SITE_OK (echo       Site server ready.) else (echo       WARNING: site server not ready - check the EGE Site window.)
start "" http://127.0.0.1:8080/index-login.html

echo Keep this window and the bridge windows open.
pause