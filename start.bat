@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Install it from https://www.python.org/downloads/ ^(check "Add python.exe to PATH" during setup^), then run this file again.
  echo If this computer has no internet access, see the "Offline / air-gapped Windows
  echo install" section in README.md -- you only need to copy a Python installer here
  echo from another PC over your internal network; no other download is required.
  pause
  exit /b 1
)

if not exist .venv (
  echo First-time setup: creating a virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo Could not create a virtual environment. See the error above.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat

set REQ_HASH_FILE=.venv\.requirements.sha256
set NEW_HASH=
for /f "skip=1 delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
  if not defined NEW_HASH set NEW_HASH=%%H
)

set NEED_INSTALL=
if not defined NEW_HASH (
  set NEED_INSTALL=1
) else (
  set OLD_HASH=
  if exist "%REQ_HASH_FILE%" set /p OLD_HASH=<"%REQ_HASH_FILE%"
  if not "%NEW_HASH%"=="%OLD_HASH%" set NEED_INSTALL=1
)

set OFFLINE_WHEELS=vendor\wheels

if defined NEED_INSTALL (
  if exist "%OFFLINE_WHEELS%\*.whl" (
    echo Installing dependencies from the local offline package folder ^(%OFFLINE_WHEELS%^)...
    echo No internet connection is needed or used for this step.
    pip install --quiet --no-index --find-links="%OFFLINE_WHEELS%" -r requirements.txt
    if errorlevel 1 (
      echo.
      echo Could not install dependencies from %OFFLINE_WHEELS%.
      echo Check that the folder contains the .whl files from the offline package bundle
      echo described in the "Offline / air-gapped Windows install" section of README.md.
      pause
      exit /b 1
    )
  ) else (
    if not defined COLLECTION_DATA_PIP_INDEX_URL set COLLECTION_DATA_PIP_INDEX_URL=https://pypi.org/simple
    echo Installing dependencies ^(first run only, this can take a minute^)...
    echo Using package index: %COLLECTION_DATA_PIP_INDEX_URL%
    python -m pip install --quiet --no-cache-dir --index-url %COLLECTION_DATA_PIP_INDEX_URL% --upgrade pip
    if errorlevel 1 (
      echo.
      echo Could not upgrade pip. See the error above.
      echo If your network requires a private package mirror, set the
      echo COLLECTION_DATA_PIP_INDEX_URL environment variable to it and run this file again.
      echo If this computer has no internet access at all, see the "Offline / air-gapped
      echo Windows install" section in README.md instead -- it skips this step entirely.
      pause
      exit /b 1
    )
    pip install --quiet --no-cache-dir --index-url %COLLECTION_DATA_PIP_INDEX_URL% -r requirements.txt
    if errorlevel 1 (
      echo.
      echo Could not install dependencies. See the error above.
      echo This usually means pip resolved an outdated or broken package index ^(for
      echo example, a stale corporate mirror^). The default index above is the real
      echo pypi.org, which should have everything needed. If your network requires a
      echo private mirror instead, set the COLLECTION_DATA_PIP_INDEX_URL environment
      echo variable to it and run this file again. If this computer has no internet
      echo access at all, see the "Offline / air-gapped Windows install" section in
      echo README.md.
      pause
      exit /b 1
    )
  )
  if defined NEW_HASH (
    echo %NEW_HASH% > "%REQ_HASH_FILE%"
  )
)

echo.
echo Starting Collection Data -- your browser will open automatically.
echo Keep this window open while you use Collection Data; closing it stops the server.
echo.

start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

uvicorn app.main:app --host 127.0.0.1 --port 8000

pause
