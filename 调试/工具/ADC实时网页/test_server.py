import unittest
from unittest.mock import patch
import subprocess
from server import SERIAL, parse_sample, read_sample


class SamplingTests(unittest.TestCase):
    def test_real_format_and_conversion(self):
        sample = parse_sample(SERIAL + '\x00ff3c0000.saradc\r\r\n1.757812500\n1023\n355\n', SERIAL)
        self.assertAlmostEqual(sample['voltage'][0], 1.7982421875)
        self.assertAlmostEqual(sample['voltage'][1], 0.6240234375)

    def test_reject_bad_identity_and_invalid_values(self):
        for values in [('wrong', '1.7', '10', '10'), (SERIAL, 'nan', '10', '10'),
                       (SERIAL, '1.7', '1024', '10'), (SERIAL, '1.7', 'bad', '10')]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                parse_sample(' '.join((values[0], 'ff3c0000.saradc', *values[1:])), SERIAL)

    def test_disconnected_device_does_not_return_old_values(self):
        with patch('server.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'device offline')):
            with self.assertRaisesRegex(ValueError, 'device offline'):
                read_sample('adb', SERIAL)


if __name__ == '__main__':
    unittest.main()
