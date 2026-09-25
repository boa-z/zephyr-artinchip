# SPDX-License-Identifier: Apache-2.0
"""Build an offline standalone probe and FIT. No flash image or device access."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from elftools.elf.elffile import ELFFile
from evidence import record
from zephyr_fit import encode, verify


def build(toolchain, output):
    root = Path(__file__).resolve().parents[1]
    source = root / 'diagnostics/jump_probe'
    output.mkdir(parents=True, exist_ok=False)
    prefix = toolchain / 'riscv64-zephyr-elf-'
    tool = lambda name: str(prefix) + name + '.exe'
    elf = output/'probe.elf'
    command = [tool('gcc'), '-march=rv32imac_zicsr', '-mabi=ilp32', '-nostdlib',
               '-Wl,--no-relax', '-Wl,--build-id=none', '-T', str(source/'link.ld'),
               str(source/'entry.S'), '-o', str(elf)]
    result = subprocess.run(command, capture_output=True, text=True)
    (output/'build.log').write_text(result.stdout+result.stderr)
    result.check_returncode()
    subprocess.run([tool('objcopy'), '-O', 'binary', str(elf), str(output/'probe.bin')], check=True)
    with elf.open('rb') as stream:
        image = ELFFile(stream)
        spans = [s for s in image.iter_segments() if s['p_type'] == 'PT_LOAD']
        if (image['e_entry'] != 0x40000000 or len(spans) != 1 or
                spans[0]['p_vaddr'] != 0x40000000 or spans[0]['p_paddr'] != 0x40000000 or
                spans[0]['p_memsz'] != spans[0]['p_filesz'] or
                spans[0]['p_memsz'] > 1397820):
            raise ValueError('probe ELF outside fixed profile')
        raw = (output/'probe.bin').read_bytes()
        if spans[0].data() != raw:
            raise ValueError('ELF/BIN mismatch')
    fit = encode(raw, 0x40000000, 0x40000000)
    verify(fit, raw, 0x40000000, 0x40000000)
    (output/'probe.itb').write_bytes(fit)
    (output/'disassembly.txt').write_bytes(subprocess.check_output([tool('objdump'), '-d', str(elf)]))
    report = {'scope': 'offline standalone entry probe; not a burnable delivery',
              'command': command, 'hardware_validation': 'pending', 'loadable_image': False,
              'source': {p.name: record(p.read_bytes()) for p in source.iterdir() if p.is_file()},
              'files': {p.name: record(p.read_bytes()) for p in output.iterdir() if p.is_file()}}
    (output/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.toolchain, args.output), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
