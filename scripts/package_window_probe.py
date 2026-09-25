# SPDX-License-Identifier: Apache-2.0
"""Fixed experimental Zephyr probe in the exercised product address window."""
import argparse
import io
import json
from pathlib import Path
import sys
from elftools.elf.elffile import ELFFile
from evidence import record
from image_roundtrip import BASELINE
from test_image import replace_os, verify_replacement
from zephyr_fit import encode, verify, reconstruct_binary

ELF_SHA = 'a73a0a4c94f30656476e01251e0dd60b53a38ae99d64c799ed3041fd2b647978'
BIN_SHA = '6a3d20d6b41644f3953b027e841425195e017c7e02287e79d9810f6846df6fd2'


def package(reference, elf_data, raw):
    for data, expected in ((reference, BASELINE), (elf_data, ELF_SHA), (raw, BIN_SHA)):
        if record(data)['sha256'] != expected:
            raise ValueError('unreviewed reference or experimental probe')
    elf = ELFFile(io.BytesIO(elf_data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    if len(segments) != 1:
        raise ValueError('single load segment required')
    segment = segments[0]
    entry = elf['e_entry']
    reconstructed = reconstruct_binary(elf, 0x40000000, len(raw),
                                       ['--gap-fill', '0xFF', '--output-target=binary',
                                        '--remove-section=.comment', '--remove-section=COMMON'])
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name('aic_handoff_entry')
    if (elf.elfclass != 32 or elf['e_machine'] != 'EM_RISCV' or
            segment['p_paddr'] != 0x40000000 or segment['p_vaddr'] != 0x40000000 or
            not 0 < segment['p_filesz'] <= segment['p_memsz'] <= 65536 or
            reconstructed != raw or not segment['p_flags'] & 1 or
            not 0x40000000 <= entry < 0x40000000 + len(raw) or
            not symbols or entry != symbols[0]['st_value']):
        raise ValueError('experimental entry/memory/BIN binding mismatch')
    fit = encode(raw, 0x40000000, entry)
    verify(fit, raw, 0x40000000, entry)
    output = replace_os(reference, fit)
    report = verify_replacement(reference, output, fit)
    report.update(status='OFFLINE_VERIFIED',
                  scope='experimental Zephyr startup in product window; default SRAM not validated',
                  manual_experiment_ready=True, loadable_image=False,
                  elf=record(elf_data), binary=record(raw), entry=entry,
                  memory_start=0x40000000, memory_end=0x40000000 + segment['p_memsz'],
                  limits='No Zephyr hardware acceptance until a complete main-stage trace is inspected')
    return output, fit, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True, help='directory containing zephyr.elf/bin')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        image, fit, report = package(args.reference.read_bytes(),
                                    (args.build/'zephyr.elf').read_bytes(),
                                    (args.build/'zephyr.bin').read_bytes())
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output/'D50T_Zephyr_product_window_probe.img'
        path.write_bytes(image)
        if path.read_bytes() != image:
            raise ValueError('written image differs')
        (args.output/'probe.itb').write_bytes(fit)
        (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
