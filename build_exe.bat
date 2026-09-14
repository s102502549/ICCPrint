@echo off
setlocal
cd /d "%~dp0"
set "NO_PAUSE=0"
if /I "%~1"=="/nopause" set "NO_PAUSE=1"

if not exist ".venv\Scripts\python.exe" (
    echo Run install_and_run.bat first to create the environment.
    goto :error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

rmdir /s /q build 2>nul
rmdir /s /q dist\ICCPrint 2>nul

echo Building Windows executable folder...
python -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name ICCPrint ^
  --collect-all pypdfium2 ^
  --hidden-import PySide6.QtPrintSupport ^
  main.py
if errorlevel 1 goto :error

copy /y README.md "dist\ICCPrint\README.md" >nul
copy /y README_zh-TW.md "dist\ICCPrint\README_zh-TW.md" >nul
copy /y THIRD_PARTY_NOTICES.md "dist\ICCPrint\THIRD_PARTY_NOTICES.md" >nul
copy /y LICENSE "dist\ICCPrint\LICENSE" >nul
python scripts\collect_licenses.py "dist\ICCPrint\third_party_licenses"
if errorlevel 1 goto :error

echo.
echo Done: dist\ICCPrint\ICCPrint.exe
if "%NO_PAUSE%"=="0" pause
exit /b 0

:error
echo.
echo Build failed. Keep the error messages shown above.
if "%NO_PAUSE%"=="0" pause
exit /b 1
