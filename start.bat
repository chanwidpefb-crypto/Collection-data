@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Install it from https://www.python.org/downloads/ ^(check "Add python.exe to PATH" during setup^), then run this file again.
  pause
  exit /b 1
)

if not exist .venv (
  echo First-time setup: creating a virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

set REQ_HASH_FILE=.venv\.requirements.sha256
set NEW_HASH=
for /f "skip=1 delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
  if not defined NEW_HASH set NEW_HASH=%%H
)

if not defined NEW_HASH (
  echo Installing dependencies ^(first run only, this can take a minute^)...
  python -m pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
) else (
  set OLD_HASH=
  if exist "%REQ_HASH_FILE%" set /p OLD_HASH=<"%REQ_HASH_FILE%"
  if not "%NEW_HASH%"=="%OLD_HASH%" (
    echo Installing dependencies ^(first run only, this can take a minute^)...
    python -m pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    > "%REQ_HASH_FILE%" echo %NEW_HASH%
  )
)

echo.
echo Starting Collection Data -- your browser will open automatically.
echo Keep this window open while you use Collection Data; closing it stops the server.
echo.

start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

uvicorn app.main:app --host 127.0.0.1 --port 8000

pause
