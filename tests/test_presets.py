import unittest

from iccprint.presets import DEFAULTS, normalize_preset, validate_value


class PresetTests(unittest.TestCase):
    def test_defaults_are_complete_and_driver_ack_excluded(self):
        self.assertEqual(normalize_preset({}), DEFAULTS)
        self.assertNotIn('no_color_adjust_ack', normalize_preset({'no_color_adjust_ack': True}))

    def test_native_settings_string_numbers_are_normalized(self):
        result = normalize_preset({'dpi': '600', 'custom_w_mm': '101.6', 'bpc': 'false'})
        self.assertEqual(result['dpi'], 600)
        self.assertEqual(result['custom_w_mm'], 101.6)
        self.assertIs(result['bpc'], False)

    def test_invalid_entries_are_rejected_before_application(self):
        for value in (None, [], 'preset', {'dpi': 'oops'}, {'dpi': True}, {'dpi': 1000},
                      {'dpi': 300.5}, {'custom_w_mm': float('nan')}, {'bpc': 'yes'},
                      {'orientation': 'sideways'}, {'profile': '\x00bad'}, {'profile': None}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_preset(value)

    def test_values_are_validated_without_mutating_input(self):
        data = {'scale': 'fill', 'profile': 'printer.icc', 'dpi': '150'}
        original = dict(data)
        result = normalize_preset(data)
        self.assertEqual(data, original)
        self.assertEqual(result['scale'], 'fill')
        with self.assertRaises(ValueError):
            validate_value('unknown', 1)


if __name__ == '__main__':
    unittest.main()
