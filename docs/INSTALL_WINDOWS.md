# Windows installation and builds

## Portable package: no Python needed

Target: Windows 10/11, x64, with the printer manufacturer's Windows driver. The application UI is primarily Traditional Chinese. Native ARM64 builds are not provided.

1. Obtain the versioned `ICCPrint-<version>-Windows-x64.zip` and matching `.sha256` from a trusted distributor or a successful repository Actions build. A source checkout is not a prebuilt executable.
2. Optionally compare `Get-FileHash .\ICCPrint-0.3.0-Windows-x64.zip -Algorithm SHA256` with the supplied checksum. A checksum detects changed bytes; it is not a code signature or proof of publisher identity.
3. Extract the **entire** archive. Open the `ICCPrint` folder and run `ICCPrint.exe`. Keep `_internal`, `docs`, and notices with the executable; do not copy only the EXE or launch it inside the ZIP.
4. Read `START_HERE.txt` and follow [the first-print workflow](USER_GUIDE.md). No Python, LibreOffice, or printer profile is bundled as a separate installer. Python and required runtime libraries are inside `_internal`; install LibreOffice separately only if Office conversion is needed.

ICCPrint does not require administrator privileges. Printer-driver installation may. Builds are unsigned unless a distributor separately signs and documents them. If Windows security blocks a download, verify the source and ask your administrator or maintainer; do not automatically bypass security warnings.

Settings use the current user's `ICCPrint/ICCPrint` Qt settings store (normally `HKEY_CURRENT_USER\Software\ICCPrint\ICCPrint` on Windows). Documents are processed locally; converted Office documents are temporary. Removing the extracted application folder removes the program but does not erase saved settings or original documents.

## Run from source

Install x64 Python **3.12 or 3.13**, then clone or extract this repository to a writable folder:

```bat
install_and_run.bat
```

The script creates `.venv`, installs the tested dependency set, and launches the app. Future launches can use `run.bat`. Setup needs internet access to the Python package index; normal document processing does not upload files.

Manual equivalent:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m iccprint
```

If an old `.venv` uses an unsupported Python version, close ICCPrint, rename the environment, and recreate it with a supported interpreter. The app's settings are separate from this environment.

## Build a portable Windows package

On native x64 Windows with Python 3.12 or 3.13, run:

```bat
build_exe.bat
```

No prior source setup is needed. The builder:

1. Recreates its own `build\windows\venv` and installs pinned runtime and packaging dependencies. It leaves the development `.venv` alone.
2. Runs dependency checks, compilation, and all headless tests.
3. Builds an onedir application with Windows file/product version metadata, copies first-run instructions, documentation, and dependency notices, and exercises the actual executable's native libraries.
4. Validates the bundle, writes `BUILD_MANIFEST.json` with the commit, Python and package versions, and every bundled file's SHA-256, then creates the ZIP and its checksum.

Outputs:

```text
dist/ICCPrint/ICCPrint.exe
dist/ICCPrint/START_HERE.txt
dist/ICCPrint/BUILD_MANIFEST.json
dist/ICCPrint/third_party_licenses/
dist/ICCPrint-0.3.0-Windows-x64.zip
dist/ICCPrint-0.3.0-Windows-x64.zip.sha256
```

`build_exe.bat /nopause` is suitable for CI. The Windows artifact workflow additionally extracts the ZIP, rechecks the file inventory, and runs the extracted executable's smoke test. It uploads an artifact; it does **not** publish a release or tag.

### Reproducibility boundary

`requirements-lock.txt`, `requirements-build.txt`, and build-system pins fix the Python dependency versions. Archive ordering, permissions and timestamps are normalized using `SOURCE_DATE_EPOCH`, or the latest commit time. These are repeatable build inputs, not a claim of bit-identical native executables across Python patch versions, Windows images, compiler/bootloader builds or signing. The manifest records the exact environment. Preserve the build logs and checksum alongside any distributed binary; rebuild and test after changing pins.

Read [the release checklist](RELEASE_CHECKLIST.md) before redistributing. Successful automated tests do not replace a clean Windows launch, native print-dialog checks, physical-printer testing, or review of dependency source/license obligations.
