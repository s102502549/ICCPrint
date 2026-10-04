# First print and repeatable settings

## 1. Prepare the print condition

Use the ICC made for your exact printer, ink and paper. Record the profiling media type, quality, and other driver settings. Install the manufacturer driver and begin with a single test page. ICCPrint cannot inspect whether a vendor's color-correction option is disabled.

New application installations use Relative Colorimetric with Black Point Compensation. This is a starting point, not a universal recommendation for every profile. Existing valid saved settings are retained.

## 2. Add and inspect documents

Use **加入檔案…** or drag files into the window. Supported images and PDFs are processed locally; Office files use an installed LibreOffice to create temporary PDFs. Check converted layout carefully, especially fonts and pagination.

Select a file, move through its pages with the preview navigation or direct page number, reorder the document queue, and remove unwanted files. Preview/import work is asynchronous; changing settings requests a new preview and obsolete results are ignored. A corrupt page or invalid embedded profile can still fail later rendering, so successful import is not a guarantee that every page is printable.

## 3. Select ICC and color options

Choose an installed profile or use **瀏覽 ICC…**. **檢查 ICC** checks RGB printer-output classification, supported intent and conversion availability. Monitor/sRGB profiles and CMYK output profiles are not acceptable substitutes.

The **ICC 軟打樣** checkbox switches between:

- Source preview: the source is color-managed to sRGB for display, without printer simulation
- Proof preview: printer-profile simulation converted back to sRGB

Neither view automatically applies a monitor profile. Inspect profile identity, intent, BPC and the information/warnings accompanying the preview. See [color management](COLOR_MANAGEMENT.md) for embedded-profile and PDF behavior.

## 4. Paper and physical size

Set paper and portrait/landscape orientation; custom paper uses millimeters. Match these with the native driver dialog.

- Fit keeps all content on the paper
- Fill intentionally crops content to fill the paper
- Actual 100% keeps physical dimensions and can clip oversized content

PDFs use their physical page dimensions. Images use embedded DPI, or the fallback DPI you set when metadata is missing. The PDF/Office rasterization DPI controls detail/memory, independently of PDF physical size. Warnings about effective resolution and clipping are prompts to review the layout, not guarantees of physical print quality.

The preview is the full sheet. The driver's non-printable region can clip that sheet, even when a preview looks correct. Make a physical-size test before dimension-critical output.

## 5. Save a repeatable preset

Use **列印預設 → 儲存目前設定…**, give the setup a descriptive name (for example printer + paper + quality), then restore it with **套用已儲存設定…**. A preset stores application values: ICC path, intent, BPC, raster/fallback DPI, paper, custom size, orientation and layout.

Presets do not copy the ICC file, embed documents, change manufacturer driver properties, or guarantee that a moved profile still exists. The driver color-correction acknowledgment is never saved/restored. Recheck profile availability and driver settings whenever applying a preset or changing the print condition.

## 6. Preflight and submit

The readiness panel checks loaded pages, the output profile and driver acknowledgment. Confirm **我會在印表機驅動中關閉額外色彩校正**, then choose **列印…**. In the native dialog choose the printer, page range, copies and collating, and match the profiled paper/media/quality.

Before starting the printer job, ICCPrint renders and color-converts all selected pages into temporary PNGs. A later invalid source page therefore fails preparation instead of partially submitting an otherwise unvalidated document. Source-file signatures are checked during preparation; if a source changes, the job is rejected rather than mixing old and new content. This needs temporary disk space proportional to the job. Rendering safety limits still apply; reducing DPI reduces memory and disk use.

Preparation and submission show progress. Cancel is cooperative between processing stages; a single native render/conversion may need to finish before cancellation is observed. During submission, cancellation stops unsent pages and asks the driver to abort. Already submitted or physically printed pages cannot be recalled; inspect the Windows queue before retrying.

A completion message means the application finished submitting to the print queue. It does not confirm paper movement, ink delivery or physical completion. Inspect the physical result and record settings before printing the rest.

## Local data and cleanup

Settings/presets are local per-user Qt settings. Originals are not overwritten. Office conversions and prepared pages use temporary storage and are cleaned up when their document/job is released or the application exits normally. A forced termination, power loss or OS crash may leave temporary files; review stale temporary directories only after the application has exited, taking care not to delete other work.
