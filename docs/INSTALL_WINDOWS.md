# Windows installation

## Requirements

- Windows 10 or Windows 11
- 64-bit Python 3.12 or 3.13
- A Windows printer driver for the target printer
- An RGB printer ICC/ICM profile
- Optional: LibreOffice if you want ICCPrint to open Word, Excel, or PowerPoint files directly

## Easy setup

Run:

```bat
install_and_run.bat
```

The script creates `.venv`, installs the Python dependencies, and launches ICCPrint.

After setup, use:

```bat
run.bat
```

## Manual setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

## Building the Windows folder distribution

```bat
build_exe.bat
```

The result is written to `dist\ICCPrint`.

The folder build is intentionally used instead of a one-file executable because it makes bundled dependencies and third-party licenses easier to inspect and redistribute correctly.
