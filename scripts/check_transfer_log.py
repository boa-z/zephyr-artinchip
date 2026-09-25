# SPDX-License-Identifier: Apache-2.0
"""Strict schema-2 transfer evidence checker; does not authorize hardware use."""
import argparse
import json
from pathlib import Path
import re
import sys
from evidence import record


def check(data):
    lines = data.decode('utf-8', errors='strict').splitlines()
    begin = 'H0-SPL begin schema=2 instrumentation=active acceptance=pending'
    if lines.count(begin) != 1 or sum(x.startswith('H0-SPL begin') for x in lines) != 1:
        raise ValueError('expected one schema-2 attempt')
    starts = [i for i, x in enumerate(lines) if x.startswith('H0-SPL entry=')]
    if len(starts) != 1 or starts[0] <= lines.index(begin):
        raise ValueError('missing or duplicate dump')
    start = starts[0]
    match = re.fullmatch(r'H0-SPL entry=00000000 count=(\d+) dropped=0', lines[start])
    if not match or not 1 <= int(match[1]) <= 256:
        raise ValueError('invalid count, entry or dropped records')
    count = int(match[1])
    events = []
    for i, line in enumerate(lines[start + 1:start + 1 + count]):
        m = re.fullmatch(r'H0-E (\d+) (\d+) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8})', line)
        if not m or int(m[1]) != i:
            raise ValueError('malformed or reordered event')
        events.append((int(m[2]), *(int(m[j], 16) for j in (3, 4, 5))))
    if len(events) != count or sum(x.startswith('H0-E ') for x in lines) != count:
        raise ValueError('event count mismatch')
    if lines[start + count + 1:start + count + 3] != [
        'H0-SPL end evidence=CAPTURED hardware=pending',
        'H0-TRANSFER-ONLY: FIT attempt ended; no payload jump; return to console']:
        raise ValueError('missing terminal markers')

    def snapshot(pos, stage):
        expected = [(10, stage, None), (11, stage, None), (12, 0x18000160, stage)]
        expected += [(13, 0x2ffff000 + 4*i, stage) for i in range(16)]
        expected += [(14, 0x10000100 + 0x40*i, stage) for i in range(8)]
        chunk = events[pos:pos + 27]
        if len(chunk) != 27:
            raise ValueError('truncated snapshot')
        for (kind, addr, size), (k, a, s, r) in zip(expected, chunk):
            if (kind, addr) != (k, a) or (size is not None and size != s):
                raise ValueError('snapshot register/stage mismatch')
            if k == 14 and r:
                raise ValueError('sampled DMA channel enabled')
        return pos + 27

    pos = snapshot(0, 1)
    current = None
    allocated = {}
    pending = None
    needs_crc = None
    reads = []
    payloads = []
    stop_count = 0
    awaiting_payload = False
    while pos < len(events):
        k, a, s, r = events[pos]
        if k == 10:
            if current or allocated or pending or needs_crc or awaiting_payload:
                raise ValueError('snapshot inside unfinished operation')
            pos = snapshot(pos, 2)
            awaiting_payload = True
            continue
        if k == 3:
            if not awaiting_payload or pending or not s or a + s > 2**32:
                raise ValueError('invalid payload interval/order')
            pending = (a, s, r)
            awaiting_payload = False
        elif k == 1:
            if current or awaiting_payload or needs_crc or not a or not s or a + s > 2**32:
                raise ValueError('invalid/nested read')
            if pending and pending != (a, s, r):
                raise ValueError('payload/read mismatch')
            current = (a, s, r)
        elif k == 4:
            if not current or not a or not s or r or a in allocated or a + s > 2**32:
                raise ValueError('invalid allocation')
            if any(a < b + n and b < a + s for b, n in allocated.items()):
                raise ValueError('overlapping allocations')
            allocated[a] = s
        elif k == 5:
            if not current or a not in allocated or s or r:
                raise ValueError('unmatched free')
            del allocated[a]
        elif k == 16:
            if not current or not a or not s or r:
                raise ValueError('invalid/failed DMA stop summary')
            stop_count += s
        elif k == 2:
            # SPI NAND mtd_read forwards spinand_read's status, not bytes read.
            # Zero alone does not prove full length (MTD can clamp a request).
            if not current or (a, s) != current[:2] or r != 0 or allocated:
                raise ValueError('failed/unpaired NAND read or live buffer')
            reads.append(current)
            if pending:
                needs_crc = pending
                pending = None
            current = None
        elif k == 8:
            if not needs_crc or (a, s) != needs_crc[:2] or not r:
                raise ValueError('unpaired CRC evidence')
            payloads.append({'address': a, 'size': s, 'offset': needs_crc[2], 'crc32': r})
            needs_crc = None
        elif k == 7:
            if (a, s, r) != (0, 0, 0) or current or allocated or pending or needs_crc or awaiting_payload:
                raise ValueError('failed/incomplete FIT attempt')
            pos = snapshot(pos + 1, 3)
            if pos != len(events) or len(reads) < 3 or not payloads or not stop_count:
                raise ValueError('incomplete transfer evidence')
            return {'log_validation': 'PASS', 'log': record(data), 'payloads': payloads,
                    'read_count': len(reads), 'reads': reads, 'dma_stop_count': stop_count,
                    'read_result_semantics': 'SPI NAND status: zero success; not a byte count',
                    'loadable_image': False, 'hardware_validation': 'pending',
                    'limits': 'Text consistency only; CRC and identity need image binding; no alias or all-bus-master proof'}
        else:
            raise ValueError('unknown or out-of-order event')
        pos += 1
    raise ValueError('missing FIT completion')


def check_original(data):
    result = check(data)
    expected = [{'address': 0x40000000, 'size': 1397820, 'offset': 0x800, 'crc32': 0xf183bd17}]
    reads = result['reads']
    if result['payloads'] != expected or len(reads) != 3:
        raise ValueError('trace differs from original-product payload profile')
    for (address, size, offset), length in zip(reads[:2], (40, 732)):
        if size != length or offset or not 0x40c80000 <= address <= 0x41000000-size:
            raise ValueError('metadata read differs from original-product profile')
    result['profile'] = 'original-product b0062dac; reported fields match, not a flash readback'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check_original(args.log.read_bytes()), indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'log_validation': 'FAIL', 'error': str(error)}))
        sys.exit(1)
