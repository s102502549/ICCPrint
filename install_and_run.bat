@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo ICCPrint - first-time setup and launch
echo =============================================

echo.
echo Looking for Python...
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
if not defined PY_CMD goto :no_python

%PY_CMD% -c "import sys, struct; sys.exit(0 if sys.version_info[:2] in ((3, 12), (3, 13)) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto :unsupported_python

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

echo Installing or updating required packages...
python -c "import sys, struct; sys.exit(0 if sys.version_info[:2] in ((3, 12), (3, 13)) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto :unsupported_python
python -m pip install pip==26.2.1
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python -m pip check
if errorlevel 1 goto :error

echo Starting ICCPrint...
python main.py
exit /b %errorlevel%

:unsupported_python
echo Supported: x64 Python 3.12 or 3.13.
echo If .venv uses another version, close the app and rename .venv before retrying.
goto :error

:no_python
echo.
echo Python was not found.
echo Install 64-bit Python 3.12 or 3.13 from python.org.
echo During setup, enable "Add python.exe to PATH".
echo Then run this file again.
echo.
pause
exit /b 1

:error
echo.
echo Setup failed. Keep the error messages shown above.
pause
exit /b 1
