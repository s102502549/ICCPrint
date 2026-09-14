# Color-management workflow

ICCPrint is designed around application-managed printer color conversion.

## Output pipeline

```text
Source file
  -> embedded source ICC, or sRGB fallback
  -> selected rendering intent
  -> optional Black Point Compensation
  -> selected RGB printer ICC/ICM
  -> Windows print dialog / printer driver
  -> printer
```

The printer driver should not perform a second color conversion. If the driver provides a setting such as `No Color Adjustment`, use it.

## Rendering intents

ICCPrint exposes all four standard ICC rendering intents supported by Pillow/LittleCMS:

- Perceptual
- Relative Colorimetric
- Saturation
- Absolute Colorimetric

A printer profile may not implement every intent. ICCPrint checks whether the selected output profile reports support for the chosen intent.

## Black Point Compensation

BPC remaps the source black point to the destination black point to preserve more usable shadow gradation when source and printer black points differ. It is commonly paired with Relative Colorimetric, but ICCPrint allows it with the other intents so users can compare actual output.

## Soft proofing

The preview uses the selected printer profile as a proofing profile and converts the simulated result back to sRGB for display. This is useful for comparing settings, but it is not a substitute for a calibrated monitor and controlled viewing conditions.

## Profile validity depends on the print condition

A printer ICC profile is only valid for the print condition used to create it. Keep the following consistent:

- printer
- ink set
- paper
- media type selected in the driver
- print quality / resolution
- relevant high-speed or bidirectional options
- any other driver setting that changes ink laydown
