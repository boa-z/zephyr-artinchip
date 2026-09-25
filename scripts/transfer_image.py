# SPDX-License-Identifier: Apache-2.0
"""Package one reviewed original-product transfer-stop loader; no device IO."""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib
from audit_loader import container_components, cstring, loader_layout, overlaps
from evidence import record
from image_roundtrip import BASELINE
from observation_image import wrap_loader, verify_wrapped, verify_image, word

LOADER = '333266456097713f133874dae4afc0fa0b759852c6dfe249a99d4741c2488057'


def build(reference, old_bin, elf, raw):
    if record(reference)['sha256'] != BASELINE or record(raw)['sha256'] != LOADER:
        raise ValueError('unreviewed image or loader profile')
    _, _, _, spans = loader_layout(elf, raw)
    payload = {'start': 0x40000000, 'end': 0x4015543c}
    if spans[0]['end'] > 0x40c80000 or overlaps([payload], spans):
        raise ValueError('loader/heap/payload overlap')
    components = container_components(reference)
    item = components['image.target.spl']
    start, end = item['offset'], item['offset'] + item['size']
    original = reference[start:end]
    wrapped = wrap_loader(original, old_bin, raw)
    verify_wrapped(original, wrapped, raw)
    if len(wrapped) > item['size']:
        raise ValueError('loader exceeds fixed slot')
    meta, length = struct.unpack_from('<2I', reference, 332)
    slots = [n for n in range(meta, meta + length, 512)
             if cstring(reference[n+8:n+72]) == 'image.target.spl']
    if len(slots) != 1 or len(wrapped) > word(reference, slots[0]+108):
        raise ValueError('partition capacity mismatch')
    output = bytearray(reference)
    output[start:end] = wrapped + b'\xff' * (item['size'] - len(wrapped))
    struct.pack_into('<2I', output, slots[0]+140, len(wrapped), zlib.crc32(wrapped))
    verify_image(reference, output, wrapped)
    return bytes(output), {'scope': 'original-product H0 transfer-stop; no payload execution',
                          'offline_verification': 'PASS', 'loadable_image': False,
                          'hardware_validation': 'pending', 'image': record(output),
                          'reference': record(reference), 'loader': record(raw),
                          'loader_elf': record(elf), 'loader_spans': spans,
                          'payload_span': payload, 'target_spl': record(wrapped),
                          'slot_size': item['size'], 'retained_updater': components['image.updater.spl']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('reference', 'original-bin', 'elf', 'bin', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    try:
        reference = args.reference.read_bytes()
        output, report = build(reference, args.original_bin.read_bytes(), args.elf.read_bytes(), args.bin.read_bytes())
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output/'D50T_H0_transfer_stop.img'
        path.write_bytes(output)
        if path.read_bytes() != output:
            raise ValueError('written image mismatch')
        (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        sys.exit(1)
