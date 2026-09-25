# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from check_jump_log import check


def fixture(mstatus=0):
    fields = [0x40c40000, 0, 0, 5, 0, mstatus, 0, 0x40c00383, 0x103f]
    return ('H0-JUMP schema=1 fields=9\n' +
            ''.join(f'H0-J {value:08x}\n' for value in fields) +
            'H0-JUMP STOP hardware=pending\n').encode()


class JumpTests(unittest.TestCase):
    def test_complete_is_not_hardware_acceptance(self):
        result = check(fixture())
        self.assertEqual(result['fields']['boot_device_a0'], 5)
        self.assertFalse(result['loadable_image'])

    def test_reject_incomplete_duplicate_and_bad_entry_mask(self):
        data = fixture()
        for invalid in (data[:-20], data+data, fixture(8),
                        data.replace(b'H0-J 00000005', b'H0-J x0000005')):
            with self.assertRaises(ValueError):
                check(invalid)
