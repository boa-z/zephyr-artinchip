# SPDX-License-Identifier: Apache-2.0
"""Fixed experimental Z0 stability-gate image in the observed 144-slot window.

Packages one of the three gate builds -- the MIL-heartbeat kernel suite
(--app kernel), the FPU stress matrix (--app fpu) or the sustained
kernel+FPU stress application (--app stress) -- into a flashable product image.
All three boot at __start in the same 0x40000000 64 KiB window
(samples/handoff_probe/product-window.overlay) with the SoC's 144-slot CLIC table
(soc/artinchip/d13x/Kconfig.defconfig), so they share one set of
structural binding checks. This is a sibling of the per-artifact packagers
(package_kernel_trial.py stays pinned to the round-12 baseline image and is not
modified here).

The stress application is the hardware evidence for the ten-minute gate item, so
its build must carry the 600 s profile: the QEMU coverage profile (a few
seconds) is rejected here rather than silently shipped as a hardware image.

Pinning follows the kernel r12 two-stage precedent: the first reproducible build
is packaged with --allow-unpinned, which records the computed ELF/BIN SHA-256
into verification.json; those values are then pinned per application in PINNED
below (or passed as --expect-elf-sha/--expect-bin-sha) so every later run rejects
a tampered probe. --allow-unpinned also overrides an existing PINNED entry, which
is how a deliberately new source revision is packaged: the pin is dropped, the
status becomes OFFLINE_VERIFIED_UNPINNED and unreviewed_build is true, so the
record never claims a board result for bytes that were not on the board. The
pins are keyed by --app deliberately: one shared pair would make a legitimate
kernel build fail the fpu pin and vice versa. The BASELINE product reference
check is always enforced.
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
# kernel and fpu were packaged unpinned, built for d50t_2_lite/d133ecs and then
# observed PASS on physical hardware on 2026-09-26 (kernel 9/9 with 2,101,657
# thread-state MIL samples at zero violations; fpu context matrix 1/1 with
# 5003+5004 peer preemptions), so these hashes are the reviewed gate builds.
# The stress pin is only the reviewed *build* (600 s profile, 44368 B RAM in the
# experimental window); its hardware result stays pending until the board log is
# returned. A pristine rebuild in a fresh directory reproduces the BIN and the
# packaged image byte-for-byte but changes the ELF hash, because DWARF embeds the
# build path; pass --expect-elf-sha for that case instead of treating it as
# tampering -- the BIN pin and the BASELINE check stay enforced.
PINNED = {
    'kernel': ('1ab0896753d332e0d6f1075a98512b1b068a161e1bb31e564d1b27507a2cbbe2',
               '14549f37cc4df97ed54c1281c0125f4cb60e904fbf00ca670ff4839488a7ebe3'),
    'fpu': ('04eba2449e0a0ee75fcc68f0a1ded1858848effb1c04822a6f914cefb0cc20ea',
            'a144fbb3be29610c7ed896b6adf391943755e971d4d2d6f9ede8bcbea05735dd'),
    'stress': ('a9d485e1ff8afe90376b2af88c248f6484bccc9943d96ebdb30a0474c9953c8b',
               'c0d7a411a47b6b4fe33442c5b892a4e509bad60ce377e2801b56e1332fe5939d'),
}
ENTRY_SYMBOL = '__start'
# Mirrors CONFIG_NUM_IRQS (soc/artinchip/d13x/Kconfig.defconfig); a build with any
# other table size is not the reviewed gate configuration and is rejected below.
NUM_IRQS = 144
# The experimentally exercised product window, not an inferred hardware map.
WINDOW_START = 0x40000000
WINDOW_BYTES = 65536
APPS = ('kernel', 'fpu', 'stress')
# What the board log in artifacts/ actually covers, per application. Kept next to
# the packaging code so a verification.json can never claim more than the archive.
HARDWARE_RESULT = {
    'kernel': 'kernel 9/9 observed PASS on-board (one archived round; further '
              'repeats are operator-reported without per-round logs)',
    'fpu': 'the FPU context matrix observed PASS on-board (two archived boots)',
    'stress': 'the 600 s window observed PASS on-board (log tail only: no begin '
              'line and no intermediate heartbeats archived)',
}
# Hardware evidence for the ten-minute gate item; the QEMU coverage profile is
# shorter on purpose and must never be packaged as a flashable gate image.
STRESS_DURATION_SEC = '600'
# Each negative-probe build enables exactly one of these; a gate image enables none.
INJECTABLE = ('CONFIG_AIC_Z0_STRESS_INJECT_MIL', 'CONFIG_AIC_Z0_STRESS_INJECT_FPU',
              'CONFIG_AIC_Z0_STRESS_INJECT_TIMER', 'CONFIG_AIC_Z0_STRESS_INJECT_PEER')


def config_values(config_text, key):
    return [line.split('=', 1)[1].strip() for line in config_text.splitlines()
            if line.startswith(key + '=')]


def config_setting(config_text, key):
    """Return the single explicit value of a Kconfig symbol, or raise."""
    values = config_values(config_text, key)
    if len(values) != 1:
        raise ValueError(f'{key} is {"ambiguous" if values else "absent"} in .config; '
                         'the build does not state its hardware profile')
    return values[0]


def window_binding(elf_data, raw):
    """Prove the build boots inside the experimental window, or raise.

    One executable segment at WINDOW_START, still fitting the observed
    WINDOW_BYTES, with the 144-slot tables the boot contract was built for: a
    gate build that overflows the window fails here instead of on the board.
    """
    elf = ELFFile(io.BytesIO(elf_data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    if len(segments) != 1:
        raise ValueError('single load segment required')
    segment = segments[0]
    entry = elf['e_entry']
    reconstructed = reconstruct_binary(elf, WINDOW_START, len(raw),
                                       ['--gap-fill', '0xFF', '--output-target=binary',
                                        '--remove-section=.comment', '--remove-section=COMMON'])
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name(ENTRY_SYMBOL)
    if (elf.elfclass != 32 or elf['e_machine'] != 'EM_RISCV' or
            segment['p_paddr'] != WINDOW_START or segment['p_vaddr'] != WINDOW_START or
            not 0 < segment['p_filesz'] <= segment['p_memsz'] <= WINDOW_BYTES or
            reconstructed != raw or not segment['p_flags'] & 1 or
            not WINDOW_START <= entry < WINDOW_START + len(raw) or
            not symbols or entry != symbols[0]['st_value']):
        raise ValueError('experimental entry/memory/BIN binding mismatch '
                         '(gate window overflow past 64 KiB fails here)')
    for name, size in (('_irq_vector_table', NUM_IRQS * 4), ('_sw_isr_table', NUM_IRQS * 8)):
        table = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
        if not table or table[0]['st_size'] != size:
            raise ValueError(f'{NUM_IRQS}-slot interrupt table mismatch')
    return segment, entry


def package(reference, elf_data, raw, app, image_name, expect_elf=None,
            expect_bin=None, allow_unpinned=False, config_text=None):
    if app not in APPS:
        raise ValueError(f'unknown gate app: {app}')
    duration = None
    if app == 'stress':
        if config_text is None:
            raise ValueError('stress packaging needs the build .config to prove the '
                             f'{STRESS_DURATION_SEC} s hardware profile')
        duration = config_setting(config_text, 'CONFIG_AIC_Z0_STRESS_DURATION_SEC')
        if duration != STRESS_DURATION_SEC:
            raise ValueError(f'stress build is a {duration} s coverage profile, not the '
                             f'{STRESS_DURATION_SEC} s hardware gate image')
        enabled = [key for key in INJECTABLE
                   if any(v != 'n' for v in config_values(config_text, key))]
        if enabled:
            raise ValueError(f'stress build has fault injection enabled ({" ".join(enabled)}); '
                             'a hardware gate image must run the real workload')
    if record(reference)['sha256'] != BASELINE:
        raise ValueError('reference is not the pinned known-good product image')
    elf_rec = record(elf_data)
    bin_rec = record(raw)
    default_elf, default_bin = PINNED.get(app, (None, None))
    if allow_unpinned:
        # An operator override: a new source revision legitimately differs from
        # the reviewed pin, so the pin is dropped rather than satisfied and the
        # record below says the build is unreviewed.
        default_elf = default_bin = None
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
    segment, entry = window_binding(elf_data, raw)
    fit = encode(raw, WINDOW_START, entry)
    verify(fit, raw, WINDOW_START, entry)
    output = replace_os(reference, fit)
    report = verify_replacement(reference, output, fit)
    if unreviewed:
        limits = ('Offline packaging only: this build is not the pinned reviewed '
                  'image, so no board result applies to these bytes. Its pinned '
                  'predecessor reports %s with thread-state MIL=0, and that '
                  'evidence belongs to the earlier image; loadable_image stays '
                  'false' % HARDWARE_RESULT[app])
    else:
        limits = ('Offline packaging only: this run re-checks the pinned ELF/BIN '
                  'and the window binding and adds no hardware evidence. %s with '
                  'thread-state MIL=0; the cold-boot repeats are operator-reported '
                  'without archived per-run logs, and loadable_image stays false'
                  % HARDWARE_RESULT[app])
    report.update(status='OFFLINE_VERIFIED_UNPINNED' if unreviewed else 'OFFLINE_VERIFIED',
                  app=app, image_name=image_name,
                  scope=f'experimental {app} gate build in product window; '
                        'board-default SRAM link target not validated on-board',
                  manual_experiment_ready=True, loadable_image=False,
                  unreviewed_build=unreviewed,
                  elf=elf_rec, binary=bin_rec, entry=entry,
                  memory_start=WINDOW_START, memory_end=WINDOW_START + segment['p_memsz'],
                  stress_duration_sec=duration,
                  limits=limits)
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
    config = args.build/'.config'
    try:
        image, fit, report = package(args.reference.read_bytes(),
                                    (args.build/'zephyr.elf').read_bytes(),
                                    (args.build/'zephyr.bin').read_bytes(),
                                    app=args.app, image_name=image_name,
                                    expect_elf=args.expect_elf_sha,
                                    expect_bin=args.expect_bin_sha,
                                    allow_unpinned=args.allow_unpinned,
                                    config_text=config.read_text(encoding='utf-8',
                                                                  errors='replace')
                                    if config.is_file() else None)
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
