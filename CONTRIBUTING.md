# Contributing to ICCPrint

## Development setup

Use Python 3.12 or 3.13 and the tested dependency constraints:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m iccprint
```

Linux contributors can use `python3 -m venv .venv` and `.venv/bin/python`; the automated tests run headlessly. Linux CI is not a claim of supported Linux physical printing.

## Required checks

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m compileall -q iccprint scripts main.py tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/frozen_entry.py --smoke-test smoke-test.json
```

On POSIX set `QT_QPA_PLATFORM=offscreen` before equivalent `.venv/bin/python` commands. Some Linux hosts need Qt runtime packages such as `libegl1` and `libopengl0`. GUI tests must isolate settings and temporary files; never open a physical print job as part of unattended tests.

The smoke command exercises native dependencies and preview rendering but does not test printer drivers or physical output. Windows packaging changes require `build_exe.bat /nopause` and extracted-archive verification. Follow [the release checklist](docs/RELEASE_CHECKLIST.md) for manual acceptance.

## Change checklist

- Keep changes focused and explain the user-visible reason.
- Add regression tests for color, documents, geometry, presets, background jobs, cancellations/resource cleanup, or packaging as appropriate.
- Cover invalid files, repeated clicks, rapid preview changes, cancellation, close during work, and subsequent recovery, not just the happy path.
- Keep UI wording understandable and distinguish queue submission from physical printing.
- Update both README files, user-facing guides and `CHANGELOG.md` for changed behavior.
- Document changes to source interpretation, ICC validation, intent/BPC/proofing, raster budgets, coordinates, or printer submission.
- Keep vendor-specific private driver settings out of core logic; they vary across versions.
- Never commit private documents, licensed/personal ICC profiles, printer serial numbers or credentials. Synthetic profiles used by tests must be clearly marked and must never be offered as real printer calibration.

## Dependencies and versions

`iccprint/__init__.py` is the version source; setuptools and the Windows executable metadata consume it. Update `requirements-lock.txt` for runtime versions and `requirements-build.txt` for packaging versions. Build-system versions are pinned in `pyproject.toml`; the clean builder also pins pip. Review new licenses and test the complete supported matrix after updates. Record all pins and relevant source/license review for binary distributions.

Pins improve reproducibility but do not replace vulnerability review or make different Windows/Python builds bit-identical. See [build boundaries](docs/INSTALL_WINDOWS.md#reproducibility-boundary).

## Color contract

1. Decode/rasterize and validate metadata with bounded allocations.
2. Match raster source modes to their embedded profile, or use only the documented sRGB assumption. PDFium output is treated as sRGB.
3. Convert to a valid RGB printer-output profile with explicit intent and optional BPC.
4. Prepare all selected pages before beginning submission.
5. Send device RGB values through the Windows driver; the user disables extra driver color correction.

Any change to this contract must be explicit in the PR description. Automated transform tests cannot establish physical color accuracy.
