import unittest

from iccprint.printing import layout_rects


class LayoutRectsTests(unittest.TestCase):
    def test_rejects_nonfinite_or_nonpositive_geometry(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                layout_rects(value, 297, 200, 200, "fit")
        with self.assertRaises(ValueError):
            layout_rects(210, 297, 200, 200, "actual", float("nan"), 30)
        with self.assertRaises(ValueError):
            layout_rects(210, 297, 200, 200, "unknown")

    def test_fit_landscape_and_fill_crop_preserve_center(self):
        fit = layout_rects(297, 210, 100, 200, "fit")
        self.assertAlmostEqual(fit.target_w, 105)
        self.assertAlmostEqual(fit.target_x, 96)
        fill = layout_rects(297, 210, 100, 200, "fill")
        self.assertEqual(fill.source_w, 100)
        self.assertAlmostEqual(fill.source_y * 2 + fill.source_h, 200)

    def test_missing_actual_size_falls_back_to_fit(self):
        self.assertEqual(layout_rects(210, 297, 200, 200, "actual"),
                         layout_rects(210, 297, 200, 200, "fit"))

    def test_fit_square_on_a4_portrait(self):
        r = layout_rects(210.0, 297.0, 200, 200, "fit")
        self.assertAlmostEqual(r.target_w, 210.0)
        self.assertAlmostEqual(r.target_h, 210.0)
        self.assertAlmostEqual(r.target_y, 43.5)
        self.assertAlmostEqual(r.source_w, 200.0)
        self.assertAlmostEqual(r.source_h, 200.0)

    def test_fill_square_on_a4_portrait_crops_sides(self):
        r = layout_rects(210.0, 297.0, 200, 200, "fill")
        self.assertAlmostEqual(r.target_w, 210.0)
        self.assertAlmostEqual(r.target_h, 297.0)
        self.assertGreater(r.source_x, 0.0)
        self.assertLess(r.source_w, 200.0)
        self.assertAlmostEqual(r.source_h, 200.0)

    def test_actual_preserves_physical_size(self):
        r = layout_rects(
            210.0,
            297.0,
            200,
            200,
            "actual",
            actual_width=20.0,
            actual_height=20.0,
        )
        self.assertAlmostEqual(r.target_w, 20.0)
        self.assertAlmostEqual(r.target_h, 20.0)
        self.assertAlmostEqual(r.target_x, 95.0)
        self.assertAlmostEqual(r.target_y, 138.5)

    def test_actual_can_extend_outside_paper(self):
        r = layout_rects(
            100.0,
            100.0,
            200,
            200,
            "actual",
            actual_width=120.0,
            actual_height=120.0,
        )
        self.assertAlmostEqual(r.target_x, -10.0)
        self.assertAlmostEqual(r.target_y, -10.0)


if __name__ == "__main__":
    unittest.main()
