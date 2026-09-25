# SPDX-License-Identifier: Apache-2.0
"""Check the standalone probe's fixed serial frame, not hardware acceptance."""
import argparse
import json
from pathlib import Path
import re
import sys
from evidence import record


def check(data):
    lines = data.decode('utf-8').splitlines()
    begin = 'H0-JUMP schema=1 fields=9'
    end = 'H0-JUMP STOP hardware=pending'
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise ValueError('missing/duplicate probe frame')
    start = lines.index(begin)
    block = lines[start+1:start+10]
    if (len(block) != 9 or len(lines) <= start+10 or lines[start+10] != end
            or sum(x.startswith('H0-J ') for x in lines) != 9):
        raise ValueError('incomplete probe frame')
    values = []
    for line in block:
        match = re.fullmatch(r'H0-J ([0-9a-f]{8})', line)
        if not match:
            raise ValueError('invalid field')
        values.append(int(match[1], 16))
    names = ('sp', 'gp', 'ra', 'boot_device_a0', 'boot_args_a1', 'mstatus', 'mie', 'mtvec', 'mhcr')
    fields = dict(zip(names, values))
    if fields['mstatus'] & 8:
        raise ValueError('entry MIE was enabled despite loader handoff contract')
    return {'log_validation': 'PASS', 'log': record(data), 'fields': fields,
            'hardware_validation': 'pending', 'loadable_image': False,
            'limits': 'Reported entry fields only; no privilege, alias, all-DMA or Zephyr runtime proof'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.log.read_bytes()), indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'log_validation': 'FAIL', 'error': str(error)}))
        sys.exit(1)
