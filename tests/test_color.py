import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageCms

from iccprint.color import (
    _source_profile_and_image,
    convert_to_printer_rgb,
    read_profile_info,
    softproof_to_srgb,
    source_to_srgb,
    validate_printer_profile,
)


class ColorPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        self.lab = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes()
        self.display_path = Path(self.temp.name) / "display.icc"
        self.display_path.write_bytes(self.srgb)
        # Test-only synthetic output-device ICC. This is a matrix sRGB profile,
        # not a real printer characterization and must never be shipped as one.
        self.printer_path = Path(self.temp.name) / "synthetic-printer.icc"
        self.printer_path.write_bytes(self.srgb[:12] + b"prtr" + self.srgb[16:])
        self.intent = ImageCms.Intent.RELATIVE_COLORIMETRIC

    def image(self, mode="RGB", color=(123, 42, 215)):
        image = Image.new(mode, (2, 2), color)
        self.addCleanup(image.close)
        return image

    def test_profile_inspection_does_not_claim_display_profile_is_printer(self):
        self.assertEqual(read_profile_info(self.display_path).device_class, "mntr")
        with self.assertRaisesRegex(ValueError, "prtr"):
            validate_printer_profile(self.display_path)
        info = validate_printer_profile(self.printer_path, self.intent)
        self.assertEqual(info.device_class, "prtr")
        self.assertEqual(info.color_space, "RGB")
        self.assertTrue(info.supported_intents)

    def test_test_utility_allowance_is_explicit_and_not_default(self):
        info = validate_printer_profile(self.display_path, allow_non_printer_profile=True)
        self.assertEqual(info.device_class, "mntr")
        for converter in (convert_to_printer_rgb, softproof_to_srgb):
            with self.subTest(converter=converter.__name__):
                with self.assertRaisesRegex(ValueError, "prtr"):
                    converter(self.image(), self.display_path, self.intent, False)
                with converter(self.image(), self.display_path, self.intent, False,
                               allow_non_printer_profile=True) as result:
                    self.assertEqual(result.mode, "RGB")

    def test_non_rgb_output_rejected_even_with_utility_allowance(self):
        path = Path(self.temp.name) / "lab.icc"
        path.write_bytes(self.lab)
        with self.assertRaisesRegex(ValueError, "RGB"):
            validate_printer_profile(path, allow_non_printer_profile=True)

    def test_broken_output_has_actionable_error(self):
        self.printer_path.write_bytes(b"broken ICC")
        with self.assertRaisesRegex(ValueError, "有效"):
            validate_printer_profile(self.printer_path)

    def test_invalid_or_unsupported_intents_rejected(self):
        for intent in (-1, 4, 1.0, True, "relative"):
            with self.subTest(intent=intent), self.assertRaisesRegex(ValueError, "Intent"):
                validate_printer_profile(self.printer_path, intent)
        with patch("iccprint.color.ImageCms.isIntentSupported", return_value=0):
            with self.assertRaisesRegex(ValueError, "不支援"):
                validate_printer_profile(self.printer_path, self.intent)

    def test_bad_embedded_profile_never_falls_back_to_srgb(self):
        for embedded in (b"broken", b"", "invalid non-bytes"):
            for converter in (source_to_srgb, convert_to_printer_rgb, softproof_to_srgb):
                args = () if converter is source_to_srgb else (self.printer_path, self.intent, False)
                with self.subTest(embedded=embedded, converter=converter.__name__):
                    with self.assertRaisesRegex(ValueError, "內嵌 ICC"):
                        converter(self.image(), *args, embedded_input_icc=embedded)

    def test_embedded_info_is_honored_when_argument_is_absent(self):
        image = self.image()
        image.info["icc_profile"] = b"broken"
        with self.assertRaisesRegex(ValueError, "內嵌 ICC"):
            source_to_srgb(image)
        # An explicit known profile is allowed to override the image metadata.
        with source_to_srgb(image, self.srgb) as result:
            self.assertEqual(result.getpixel((0, 0)), image.getpixel((0, 0)))

    def test_mismatched_profile_is_rejected_for_rgb_cmyk_and_gray(self):
        for image, embedded in (
            (self.image(), self.lab),
            (self.image("CMYK", (0, 0, 0, 0)), self.srgb),
            (self.image("L", 80), self.srgb),
        ):
            with self.subTest(mode=image.mode), self.assertRaisesRegex(ValueError, "不相符"):
                source_to_srgb(image, embedded)

    def test_untagged_cmyk_and_lab_require_source_profile(self):
        for mode, color in (("CMYK", (0, 100, 100, 0)), ("LAB", (100, 128, 128))):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "沒有內嵌來源 ICC"):
                source_to_srgb(self.image(mode, color))

    def test_high_bit_depth_not_silently_clipped(self):
        with self.assertRaisesRegex(ValueError, "8-bit RGB"):
            source_to_srgb(self.image("I;16", 40000))

    def test_real_lab_source_is_color_managed_into_srgb(self):
        image = self.image("LAB", (150, 175, 95))
        with source_to_srgb(image, self.lab) as actual:
            with ImageCms.profileToProfile(
                image, ImageCms.getOpenProfile(BytesIO(self.lab)), ImageCms.createProfile("sRGB"),
                renderingIntent=self.intent, outputMode="RGB", flags=ImageCms.Flags.BLACKPOINTCOMPENSATION,
            ) as expected:
                self.assertEqual(actual.tobytes(), expected.tobytes())
                self.assertEqual(ImageCms.getOpenProfile(BytesIO(actual.info["icc_profile"])).profile.xcolor_space.strip(), "RGB")

    def test_rgb_identity_and_caller_image_survives_all_conversions(self):
        image = self.image()
        image.info["icc_profile"] = self.srgb
        for converter in (source_to_srgb, convert_to_printer_rgb, softproof_to_srgb):
            args = () if converter is source_to_srgb else (self.printer_path, self.intent, True)
            with self.subTest(converter=converter.__name__), converter(image, *args) as result:
                self.assertEqual(result.tobytes(), image.tobytes())
                self.assertIsNot(result, image)
        self.assertEqual(image.getpixel((0, 0)), (123, 42, 215))

    def test_rgba_flattens_white_without_mutating_source(self):
        image = self.image("RGBA", (255, 0, 0, 128))
        image.putpixel((1, 0), (20, 30, 40, 0))
        with source_to_srgb(image, self.srgb) as result:
            self.assertEqual(result.getpixel((0, 0)), (255, 127, 127))
            self.assertEqual(result.getpixel((1, 0)), (255, 255, 255))
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 128))

    def test_premultiplied_alpha_is_unpremultiplied_before_flattening(self):
        for mode, color, expected in (
            ("RGBa", (128, 0, 0, 128), (255, 127, 127)),
            ("La", (20, 128), (147, 147, 147)),
        ):
            with self.subTest(mode=mode), source_to_srgb(self.image(mode, color)) as result:
                self.assertEqual(result.getpixel((0, 0)), expected)

    def test_gray_alpha_keeps_gray_source_profile_until_transform(self):
        image = self.image("LA", (0, 128))
        profile = SimpleNamespace(profile=SimpleNamespace(xcolor_space="GRAY"))
        with patch("iccprint.color.ImageCms.getOpenProfile", return_value=profile):
            normalized, actual_profile = _source_profile_and_image(image, b"gray fixture")
        try:
            self.assertEqual(normalized.mode, "L")
            self.assertEqual(normalized.getpixel((0, 0)), 127)
            self.assertIs(actual_profile, profile)
        finally:
            normalized.close()

    def test_keyed_rgb_and_gray_transparency_flatten_to_white(self):
        for mode, color in (("RGB", (10, 20, 30)), ("L", 40)):
            image = self.image(mode, color)
            image.info["transparency"] = color
            with self.subTest(mode=mode), source_to_srgb(image) as result:
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                self.assertNotIn("transparency", result.info)

    def test_palette_transparency_preserves_rgb_profile(self):
        image = self.image("P", 0)
        image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        image.putpixel((1, 0), 1)
        image.info["transparency"] = 0
        with source_to_srgb(image, self.srgb) as result:
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(result.getpixel((1, 0)), (0, 255, 0))

    def test_untagged_gray_assumes_srgb_ramp(self):
        with source_to_srgb(self.image("L", 79)) as result:
            self.assertEqual(result.getpixel((0, 0)), (79, 79, 79))

    def test_softproof_preserves_intents_flags_and_display_metadata(self):
        image = self.image()
        with patch("iccprint.color.ImageCms.buildProofTransform", wraps=ImageCms.buildProofTransform) as build:
            with softproof_to_srgb(image, self.printer_path, ImageCms.Intent.SATURATION, True) as result:
                profile = ImageCms.getOpenProfile(BytesIO(result.info["icc_profile"]))
                self.assertEqual(profile.profile.device_class, "mntr")
            self.assertEqual(build.call_args.kwargs["renderingIntent"], ImageCms.Intent.SATURATION)
            self.assertEqual(build.call_args.kwargs["proofRenderingIntent"], ImageCms.Intent.ABSOLUTE_COLORIMETRIC)
            self.assertTrue(build.call_args.kwargs["flags"] & ImageCms.Flags.SOFTPROOFING)
            self.assertTrue(build.call_args.kwargs["flags"] & ImageCms.Flags.BLACKPOINTCOMPENSATION)

    def test_normalized_images_close_on_transform_failures(self):
        image = self.image()
        for converter, target in (
            (source_to_srgb, "profileToProfile"),
            (convert_to_printer_rgb, "profileToProfile"),
            (softproof_to_srgb, "buildProofTransform"),
        ):
            normalized = image.copy()
            args = () if converter is source_to_srgb else (self.printer_path, self.intent, False)
            with self.subTest(converter=converter.__name__):
                with patch("iccprint.color._source_profile_and_image", return_value=(normalized, ImageCms.createProfile("sRGB"))):
                    with patch(f"iccprint.color.ImageCms.{target}", side_effect=RuntimeError("transform failed")):
                        with self.assertRaisesRegex(RuntimeError, "transform failed"):
                            converter(image, *args)
                with self.assertRaises(ValueError):
                    normalized.getpixel((0, 0))
                self.assertEqual(image.getpixel((0, 0)), (123, 42, 215))


if __name__ == "__main__":
    unittest.main()
