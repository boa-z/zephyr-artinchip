# SPDX-License-Identifier: Apache-2.0
"""Fixed reviewed standalone jump experiment, retaining the original loader."""
import argparse
import json
from pathlib import Path
import sys
from evidence import record
from image_roundtrip import BASELINE
from test_image import replace_os, verify_replacement
from zephyr_fit import verify

BIN_SHA = '28f907ce5a5b9be559aae7516d1f7145c496ef23360f4ed100d3a5f020f6f47b'
ELF_SHA = '83c2c650aa9f148fa6471947db8cc37daced5909c851aee24393d08545d4d08f'


def package(reference, binary, elf, fit):
    for data, expected in ((reference, BASELINE), (binary, BIN_SHA), (elf, ELF_SHA)):
        if record(data)['sha256'] != expected:
            raise ValueError('unreviewed reference/probe profile')
    verify(fit, binary, 0x40000000, 0x40000000)
    output = replace_os(reference, fit)
    report = verify_replacement(reference, output, fit)
    report.update(status='OFFLINE_VERIFIED',
                  scope='manual standalone H0 jump trial; not Zephyr H1',
                  manual_h0_trial_ready=True,
                  payload=record(binary), elf=record(elf),
                  entry=0x40000000, end_exclusive=0x400001b8,
                  recovery_basis='prior trials owner-confirmed; this trial pending',
                  limits='Original SPL cache/IRQ handoff retained; new execution not yet observed')
    return output, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        reference = args.reference.read_bytes()
        image, report = package(reference, (args.probe/'probe.bin').read_bytes(),
                                (args.probe/'probe.elf').read_bytes(), (args.probe/'probe.itb').read_bytes())
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output/'D50T_H0_standalone_jump.img'
        path.write_bytes(image)
        if path.read_bytes() != image:
            raise ValueError('image readback differs')
        (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
