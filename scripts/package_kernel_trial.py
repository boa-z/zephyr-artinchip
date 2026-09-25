# SPDX-License-Identifier: Apache-2.0
"""Fixed experimental kernel test image with the observed 144-slot CLIC table."""
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

ELF_SHA = '89c4f9c5377d70256d454e7b3a04a3688e34d5b5329d44751b18977b763dba5f'
BIN_SHA = '165311a7f161dcabf3af9a9059da39bd047d28ed3a3cdc1d1f3656f5c80c641c'


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
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name('__start')
    if (elf.elfclass != 32 or elf['e_machine'] != 'EM_RISCV' or
            segment['p_paddr'] != 0x40000000 or segment['p_vaddr'] != 0x40000000 or
            not 0 < segment['p_filesz'] <= segment['p_memsz'] <= 65536 or
            reconstructed != raw or not segment['p_flags'] & 1 or
            not 0x40000000 <= entry < 0x40000000 + len(raw) or
            not symbols or entry != symbols[0]['st_value']):
        raise ValueError('experimental entry/memory/BIN binding mismatch')
    for name, size in (('_irq_vector_table', 144 * 4), ('_sw_isr_table', 144 * 8)):
        table = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
        if not table or table[0]['st_size'] != size:
            raise ValueError('144-slot interrupt table mismatch')
    fit = encode(raw, 0x40000000, entry)
    verify(fit, raw, 0x40000000, entry)
    output = replace_os(reference, fit)
    report = verify_replacement(reference, output, fit)
    report.update(status='OFFLINE_VERIFIED',
                  scope='experimental kernel tests in product window; default SRAM not validated',
                  manual_experiment_ready=True, loadable_image=False,
                  elf=record(elf_data), binary=record(raw), entry=entry,
                  memory_start=0x40000000, memory_end=0x40000000 + segment['p_memsz'],
                  limits='QEMU tests passed; physical kernel/timer acceptance pending full ztest result')
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
        path = args.output/'D50T_Z0_kernel_144irq.img'
        path.write_bytes(image)
        if path.read_bytes() != image:
            raise ValueError('written image differs')
        (args.output/'probe.itb').write_bytes(fit)
        (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
