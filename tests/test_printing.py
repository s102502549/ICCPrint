import unittest

from iccprint.printing import layout_rects


class LayoutRectsTests(unittest.TestCase):
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
