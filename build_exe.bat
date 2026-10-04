@echo off
setlocal
cd /d "%~dp0"
set "NO_PAUSE=0"
if /I "%~1"=="/nopause" set "NO_PAUSE=1"
set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3.12"
)
if not defined PY_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.13 -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=py -3.13"
    )
)
if not defined PY_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
    echo Install x64 Python 3.12 or 3.13 from python.org, then try again.
    goto :error
)
%PY_CMD% scripts\build_windows.py
if errorlevel 1 goto :error
echo.
echo Done. Open dist\ICCPrint\START_HERE.txt for first-run instructions.
if "%NO_PAUSE%"=="0" pause
exit /b 0
:error
echo.
echo Build failed. Keep the error messages shown above.
if "%NO_PAUSE%"=="0" pause
exit /b 1
