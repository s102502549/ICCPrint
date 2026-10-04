# Distribution verification checklist

This is a maintainer gate, not a record that a release has passed. No release publishing, signing or tag creation is automated here.

## Rebuild and automated evidence

- [ ] Review the commit, working tree and `iccprint.__version__`; update changelog and both READMEs.
- [ ] Run the full Ubuntu and Windows Python 3.12/3.13 CI matrix at that exact commit.
- [ ] Build on x64 Windows with `build_exe.bat /nopause`; retain tests and PyInstaller warnings.
- [ ] Check `BUILD_MANIFEST.json`: expected commit, clean tree, Python, architecture and dependency pins.
- [ ] Inspect license collection warnings and [dependency sources](DEPENDENCY_SOURCES.md). Missing discovered license files are not proof that a component has no obligations.
- [ ] Verify all actual bundled Qt plugins/native libraries and transitive dependencies against their matching source distributions, licenses, notices, and source/relinking requirements. Standard LGPL/GPL texts and package metadata alone do not complete this review.
- [ ] Verify the archive checksum, extract to a new path with spaces/non-ASCII characters, verify the manifest, and run the extracted frozen smoke test.
- [ ] Review artifact contents: EXE, `_internal`, START_HERE, both READMEs, docs, changelog, MIT license, notices, Python and dependency license texts; no personal profiles/documents.

## Manual Windows acceptance (record OS, driver and device)

- [ ] Launch on a clean standard-user Windows account without development Python; confirm first-run, settings restore, and graceful close.
- [ ] Load tagged/untagged RGB images, transparent images, multipage TIFF and multipage PDF; navigate and remove documents while preview work is pending.
- [ ] Select valid and invalid profiles; switch source/proof view, intent/BPC, paper/orientation and Fit/Fill/Actual rapidly; confirm latest settings win.
- [ ] Check invalid embedded ICC, unsupported CMYK without a suitable source profile, corrupt input and oversized pages produce actionable errors.
- [ ] Inspect preflight, open/cancel the native print dialog, and check changing printer, paper, copies, and page range.
- [ ] Test a job failure/cancel and a subsequent job; verify dialogs/resources recover and the UI never promises physical completion.
- [ ] Test real print output with the intended RGB printer profile and driver color correction disabled; record exact paper/ink/media/quality and a physical-size target.
- [ ] Compare output and source/proof appearance under controlled viewing conditions. Do not claim colorimetric accuracy from automated/synthetic tests.
- [ ] Document untested printers, Windows versions, known issues and any driver-specific limitations.

## Before public redistribution

Complete the dependency review, provide any required corresponding-source materials/offers and replacement/relinking instructions, and retain the source commit/build inputs. If signing, do it before final manifest/ZIP/checksum generation and revalidate the result; the current script makes unsigned builds. Obtain explicit authorization before publishing a release. Never present a CI artifact as printer-certified software.
