# SPDX-License-Identifier: Apache-2.0
"""Fixed experimental Z0 stability-gate image in the observed 144-slot window.

Packages either gate build -- the MIL-heartbeat kernel suite (--app kernel) or
the FPU stress matrix (--app fpu) -- into a flashable product image. Both are
Zephyr ztest applications that boot at __start in the same 0x40000000 64 KiB
window (samples/handoff_probe/product-window.overlay) with the owner-reported
144-slot CLIC table (tests/<app>/product-window.conf), so they share one set of
structural binding checks. This is a sibling of the per-artifact packagers
(package_kernel_trial.py stays pinned to the round-12 baseline image and is not
modified here).

Pinning follows the kernel r12 two-stage precedent: the first reproducible build
is packaged with --allow-unpinned, which records the computed ELF/BIN SHA-256
into verification.json; those values are then pinned per application in PINNED
below (or passed as --expect-elf-sha/--expect-bin-sha) so every later run rejects
a tampered probe. The pins are keyed by --app deliberately: one shared pair would
make a legitimate kernel build fail the fpu pin and vice versa. The BASELINE
product reference check is always enforced.
"""
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

# Pin after the first reproducible gate build (cf. kernel r12 @ 49c4f5c).
# Both builds were packaged unpinned, built for d50t_2_lite/d133ecs and then
# observed PASS on physical hardware on 2026-09-26 (kernel 9/9 with 2,101,657
# thread-state MIL samples at zero violations; fpu context matrix 1/1 with
# 5003+5004 peer preemptions), so these hashes are the reviewed gate builds.
PINNED = {
    'kernel': ('1ab0896753d332e0d6f1075a98512b1b068a161e1bb31e564d1b27507a2cbbe2',
               '14549f37cc4df97ed54c1281c0125f4cb60e904fbf00ca670ff4839488a7ebe3'),
    'fpu': ('04eba2449e0a0ee75fcc68f0a1ded1858848effb1c04822a6f914cefb0cc20ea',
            'a144fbb3be29610c7ed896b6adf391943755e971d4d2d6f9ede8bcbea05735dd'),
}
ENTRY_SYMBOL = '__start'
NUM_IRQS = 144
APPS = ('kernel', 'fpu')


def package(reference, elf_data, raw, app, image_name, expect_elf=None,
            expect_bin=None, allow_unpinned=False):
    if app not in APPS:
        raise ValueError(f'unknown gate app: {app}')
    if record(reference)['sha256'] != BASELINE:
        raise ValueError('reference is not the pinned known-good product image')
    elf_rec = record(elf_data)
    bin_rec = record(raw)
    default_elf, default_bin = PINNED.get(app, (None, None))
    pinned_elf = expect_elf or default_elf
    pinned_bin = expect_bin or default_bin
    if pinned_elf and elf_rec['sha256'] != pinned_elf:
        raise ValueError(f'{app} ELF differs from the pinned reviewed build')
    if pinned_bin and bin_rec['sha256'] != pinned_bin:
        raise ValueError(f'{app} BIN differs from the pinned reviewed build')
    unreviewed = not (pinned_elf and pinned_bin)
    if unreviewed and not allow_unpinned:
        raise ValueError('unpinned gate build: pass --allow-unpinned once to '
                         'establish the baseline SHA, then pin it')
    elf = ELFFile(io.BytesIO(elf_data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    if len(segments) != 1:
        raise ValueError('single load segment required')
    segment = segments[0]
    entry = elf['e_entry']
    reconstructed = reconstruct_binary(elf, 0x40000000, len(raw),
                                       ['--gap-fill', '0xFF', '--output-target=binary',
                                        '--remove-section=.comment', '--remove-section=COMMON'])
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name(ENTRY_SYMBOL)
    if (elf.elfclass != 32 or elf['e_machine'] != 'EM_RISCV' or
            segment['p_paddr'] != 0x40000000 or segment['p_vaddr'] != 0x40000000 or
            not 0 < segment['p_filesz'] <= segment['p_memsz'] <= 65536 or
            reconstructed != raw or not segment['p_flags'] & 1 or
            not 0x40000000 <= entry < 0x40000000 + len(raw) or
            not symbols or entry != symbols[0]['st_value']):
        raise ValueError('experimental entry/memory/BIN binding mismatch '
                         '(gate window overflow past 64 KiB fails here)')
    for name, size in (('_irq_vector_table', NUM_IRQS * 4), ('_sw_isr_table', NUM_IRQS * 8)):
        table = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
        if not table or table[0]['st_size'] != size:
            raise ValueError(f'{NUM_IRQS}-slot interrupt table mismatch')
    fit = encode(raw, 0x40000000, entry)
    verify(fit, raw, 0x40000000, entry)
    output = replace_os(reference, fit)
    report = verify_replacement(reference, output, fit)
    report.update(status='OFFLINE_VERIFIED_UNPINNED' if unreviewed else 'OFFLINE_VERIFIED',
                  app=app, image_name=image_name,
                  scope=f'experimental {app} gate build in product window; '
                        'default SRAM not validated',
                  manual_experiment_ready=True, loadable_image=False,
                  unreviewed_build=unreviewed,
                  elf=elf_rec, binary=bin_rec, entry=entry,
                  memory_start=0x40000000, memory_end=0x40000000 + segment['p_memsz'],
                  limits='On-board ztest observed PASS for both gate images '
                         '(kernel 9/9, fpu context matrix) with thread-state MIL=0; '
                         'Z0 stability gate still open pending >=10 cold boots, '
                         'multi-round kernel 9/9 and >=10 min combined stress')
    return output, fit, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True, help='directory containing zephyr.elf/bin')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app', choices=APPS, required=True, help='which gate build to package')
    parser.add_argument('--image-name', help='output .img name (default D50T_Z0_<app>_gate.img)')
    parser.add_argument('--expect-elf-sha', help='pin the reviewed zephyr.elf SHA-256')
    parser.add_argument('--expect-bin-sha', help='pin the reviewed zephyr.bin SHA-256')
    parser.add_argument('--allow-unpinned', action='store_true',
                        help='first run only: record the computed SHA instead of rejecting')
    args = parser.parse_args()
    image_name = args.image_name or f'D50T_Z0_{args.app}_gate.img'
    try:
        image, fit, report = package(args.reference.read_bytes(),
                                    (args.build/'zephyr.elf').read_bytes(),
                                    (args.build/'zephyr.bin').read_bytes(),
                                    app=args.app, image_name=image_name,
                                    expect_elf=args.expect_elf_sha,
                                    expect_bin=args.expect_bin_sha,
                                    allow_unpinned=args.allow_unpinned)
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output/image_name
        path.write_bytes(image)
        if path.read_bytes() != image:
            raise ValueError('written image differs')
        (args.output/'probe.itb').write_bytes(fit)
        (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
