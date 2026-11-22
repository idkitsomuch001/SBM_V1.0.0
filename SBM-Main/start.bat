@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title SBM

set "APP=SBM"
set "VENV=.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\.requirements.sha256"
set "PY="

echo ==========================================================
echo   %APP% launcher
echo ==========================================================
echo.

rem --- 1) find Python 3.11 (or reuse our own environment) -----------------

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY=%CD%\%VENV_PY%"
        goto :have_python
    )
    echo Existing environment uses the wrong Python version, recreating it...
    rmdir /s /q "%VENV%"
)

for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys; print(sys.executable)" 2^>nul`) do set "PY=%%P"
if defined PY if exist "!PY!" goto :have_python

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :have_python
)

for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable) if sys.version_info[:2]==(3,11) else print('')" 2^>nul`) do set "PY=%%P"
if defined PY goto :have_python

echo Python 3.11 was not found. Installing it for the current user...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Python.Python.3.11 -e --scope user --silent --accept-package-agreements --accept-source-agreements
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :have_python
)

echo Downloading the Python 3.11.9 installer from python.org...
curl -L --fail -o "%TEMP%\python-3.11.9-amd64.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if errorlevel 1 goto :no_python
"%TEMP%\python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_test=0
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :have_python
)
goto :no_python

:have_python
echo Using Python: !PY!
echo.

rem --- 2) virtual environment --------------------------------------------

if not exist "%VENV_PY%" (
    echo [1/4] Creating the virtual environment...
    "!PY!" -m venv "%VENV%"
    if errorlevel 1 goto :venv_failed
) else (
    echo [1/4] Virtual environment ready.
)

echo [2/4] Preparing pip...
"%VENV_PY%" -m pip install --upgrade pip --disable-pip-version-check -q
if errorlevel 1 echo        pip upgrade skipped, continuing.

rem --- 3) dependencies (only when requirements.txt changed) ---------------

set "WANT="
for /f "usebackq delims=" %%H in (`.venv\Scripts\python.exe -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" 2^>nul`) do set "WANT=%%H"
set "HAVE="
if exist "%STAMP%" set /p HAVE=<"%STAMP%"

if defined WANT if "!WANT!"=="!HAVE!" (
    echo [3/4] Dependencies are up to date.
    goto :run_app
)

echo [3/4] Installing dependencies ^(first run downloads a few hundred MB^)...
echo.
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :deps_failed
if defined WANT (
    > "%STAMP%" echo !WANT!
) else (
    echo        Note: could not fingerprint requirements.txt, the packages
    echo        will be checked again on the next start.
)
echo.
echo        Dependencies installed.

rem --- 4) start the management window ------------------------------------

:run_app
echo [4/4] Starting %APP%...
echo.
where adb >nul 2>&1
if errorlevel 1 (
    echo        Note: adb was not found in PATH. Start your Android emulator
    echo        with ADB enabled before you press Start in the window.
    echo.
)
"%VENV_PY%" "%~dp0main.py" --desktop
if errorlevel 1 goto :run_failed
exit /b 0

:no_python
echo.
echo [ERROR] Python 3.11 could not be installed automatically.
echo         Install it from https://www.python.org/downloads/release/python-3119/
echo         and run start.bat again.
goto :end_fail

:venv_failed
echo.
echo [ERROR] The virtual environment could not be created.
echo         Close any program that uses the .venv folder and try again.
goto :end_fail

:deps_failed
echo.
echo [ERROR] Installing the dependencies failed.
echo         Check your internet connection and run start.bat again;
echo         the output above shows the reason.
goto :end_fail

:run_failed
echo.
echo [ERROR] SBM exited with an error. The output above shows the reason.

:end_fail
echo.
pause
exit /b 1
