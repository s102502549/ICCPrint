# Color-management workflow

ICCPrint is application-managed RGB printer conversion. The driver must not perform a second color conversion; configure `No Color Adjustment` or the equivalent in its own UI and use the exact profiled print condition.

## Source interpretation

Raster image ICC bytes are retained until conversion and validated against the image's source color space. Malformed profiles and incompatible image/profile combinations fail explicitly instead of silently falling back to sRGB. CMYK/Lab sources require a compatible embedded source profile; an untagged CMYK image is not safely described by an sRGB assumption. Untagged ordinary RGB/grayscale content uses the documented sRGB interpretation. Transparent content is composited on white with attention to its source color space.

PDFs (and Office files after LibreOffice conversion) are rasterized by PDFium. ICCPrint treats PDFium's resulting RGB bitmap as sRGB. It does not preserve PDF vectors, output intents, separations or individual original object profiles through the printer conversion. This is not a CMYK/RIP or production prepress workflow.

## Printer output

```text
Decode image / rasterize PDF
  -> validate embedded source profile or apply explicit sRGB assumption
  -> selected rendering intent + optional BPC
  -> selected RGB printer output ICC/ICM
  -> converted RGB page pixels
  -> Windows driver with additional color correction disabled
  -> printer
```

The output profile must report RGB device color space and the ICC printer/output class (`prtr`). Renaming a monitor or sRGB profile does not make it a printer profile. ICCPrint checks output-intent support and conversion readiness before printing.

All selected pages are rendered and converted before printer submission begins. Resource limits reject oversized raster allocations rather than risking uncontrolled memory use. Temporary disk spooling separates conversion validation from sending pages to the driver.

## Rendering intents and BPC

All four standard ICC intents are available: Perceptual, Relative Colorimetric, Saturation and Absolute Colorimetric. Their effect depends on the actual profile's tables and supported transforms. New installs default to Relative Colorimetric with BPC; existing saved choices are retained.

Black Point Compensation maps source/destination black points to help retain shadow gradation. It is commonly used with Relative Colorimetric but is not an accuracy guarantee. Compare the actual profile/output condition rather than assuming one intent works best for every image.

## Source/proof comparison

Source mode converts the source to sRGB for display. Proof mode uses the printer profile in a LittleCMS proofing transform, then converts the simulation back to sRGB. Changing preview settings is asynchronous and stale results are discarded.

The application does not automatically retrieve/apply the current monitor ICC profile. A soft proof cannot validate driver configuration, ink, paper, physical margins, or measured color accuracy. Calibrated display/viewing conditions and physical test prints remain necessary. The preview is also resolution-bounded, so it is not a full-resolution pixel inspection tool.

## The print condition is part of the profile

Keep these consistent with profile creation:

- Printer and ink set
- Physical paper and driver media type
- Quality/resolution
- High-speed/bidirectional and other settings affecting ink laydown
- Driver color-correction mode

Named application presets do not control these private driver settings. Driver acknowledgment is never automatically restored from a preset.
