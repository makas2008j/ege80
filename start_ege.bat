@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title EGE AI + Tailscale Funnel - START

echo ================================================
echo  EGE 80+ - AI bridge + Tailscale Funnel
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (echo ERROR: Python not found.&pause&exit /b 1)
where curl >nul 2>&1
if errorlevel 1 (echo ERROR: curl not found.&pause&exit /b 1)

REM -------- locate tailscale --------
set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
if not exist "%TS%" set "TS=%ProgramFiles(x86)%\Tailscale\tailscale.exe"
if not exist "%TS%" set "TS=%LOCALAPPDATA%\Tailscale\tailscale.exe"
if not exist "%TS%" (
  echo WARNING: tailscale.exe not found. Phone access via Funnel will not work.
  set "TS="
)

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

REM ---------- 2. AI bridge (port 8000) ----------
echo [2/4] Starting AI bridge on http://127.0.0.1:8000
set "BRIDGE_DIR="
if exist "%~dp0bridge" (set "BRIDGE_DIR=%~dp0bridge")
if not defined BRIDGE_DIR if exist "%~dp0ege_local_ai_bridge" (set "BRIDGE_DIR=%~dp0ege_local_ai_bridge")
if not defined BRIDGE_DIR (echo ERROR: bridge folder not found.&pause&exit /b 1)

start "EGE AI Bridge" /d "%BRIDGE_DIR%" cmd /k "set AI_TOKEN=%AI_TOKEN%&&set OLLAMA_MODEL=qwen3:8b&&set OLLAMA_VISION_MODEL=qwen2.5vl:7b&&python ai_bridge.py"

echo       Waiting for bridge...
set "BRIDGE_OK="
for /l %%I in (1,1,20) do if not defined BRIDGE_OK (
  curl -s -H "Authorization: Bearer %AI_TOKEN%" http://127.0.0.1:8000/api/ >nul 2>&1
  if not errorlevel 1 set "BRIDGE_OK=1"
  if not defined BRIDGE_OK timeout /t 1 /nobreak >nul
)
if not defined BRIDGE_OK (echo ERROR: AI bridge did not start.&pause&exit /b 1)
echo       Bridge ready.

REM ---------- 3. Tailscale Funnel ----------
echo [3/4] Enabling Tailscale Funnel -^> 8000
if not defined TS (
  echo       WARNING: Tailscale not found. Phone access disabled.
  goto :tunnel_ready
)
"%TS%" status >nul 2>&1
if errorlevel 1 (
  echo       Tailscale is not connected. Open Tailscale app and sign in.
  goto :tunnel_ready
)
"%TS%" funnel --bg 8000 >nul 2>&1
if errorlevel 1 (
  echo       WARNING: Funnel could not start. Enable Funnel once in Tailscale admin.
  goto :tunnel_ready
)
echo       Funnel running.
:tunnel_ready

echo.
echo ================================================
echo  LOCAL PC:  http://127.0.0.1:8080/index-login.html
echo  PHONE:     https://desktop-03jsujc.tail8ce031.ts.net
echo  Token file: %TOKEN_FILE%
echo ================================================
echo.

REM -------- permanent site config (Tailscale URL) --------
set "CFG_FILE=%~dp0site-config.js"
if not exist "%CFG_FILE%" (
  (
    echo window.SITE_AI = {
    echo   url: "https://desktop-03jsujc.tail8ce031.ts.net",
    echo   token: ""
    echo };
  )> "%CFG_FILE%"
  echo [config] site-config.js created with permanent Tailscale URL.
) else (
  echo [config] site-config.js exists - keeping permanent URL.
)

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

echo Keep this window and the bridge window open.
pause
