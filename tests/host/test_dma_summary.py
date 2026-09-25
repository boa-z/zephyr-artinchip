# SPDX-License-Identifier: Apache-2.0
"""Execute recorder logic natively; IRQ/CSR/MMIO behavior is not simulated."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SummaryTests(unittest.TestCase):
    def test_actual_c_count_boundaries_errors_and_overflow(self):
        compiler = shutil.which('gcc')
        if not compiler:
            self.skipTest('native gcc unavailable; target build is not a runtime test')
        source = (Path(__file__).resolve().parents[2] / 'diagnostics/tinyspl/h0_diag.c').read_text()
        event = source[source.index('void h0_event('):source.index('static uint32_t reg_read(')]
        stop = source[source.index('void h0_dma_stop('):source.index('void h0_state(')]
        harness = '''#include <stdint.h>
#include <h0_diag.h>
#include <assert.h>
struct event { uint32_t kind, address, size, result; };
static struct event events[256];
static unsigned int used, dropped, active = 1, summarize_dma = 1;
static uint32_t irq_lock(void) { return 0; }
static void irq_restore(uint32_t state) { (void)state; }
'''+event+stop+'''
int main(void) {
    assert(h0_read_allowed(0x40000000, 1397820, 0x800));
    assert(!h0_read_allowed(0x40000004, 1397820, 0x800));
    assert(!h0_read_allowed(0x40000000, 1397821, 0x800));
    assert(h0_read_allowed(0x40c80000, 40, 0));
    assert(h0_read_allowed(0x41000000-732, 732, 0));
    assert(!h0_read_allowed(0x41000000-731, 732, 0));
    assert(!h0_read_allowed(0x40c7ffff, 40, 0));
    assert(!h0_read_allowed(0xffffffff, 40, 0));
    for (unsigned i=0; i<100000; i++) {
        h0_dma_stop(0x1000, 0); h0_dma_stop(0x2000, 0);
    }
    assert(used == 2 && dropped == 0);
    assert(events[0].size == 100000 && events[1].size == 100000);
    h0_dma_stop(0x1000, 0xffffffff);
    assert(used == 3 && events[2].result == 0xffffffff);
    h0_event(2, 0, 0, 0); h0_dma_stop(0x1000, 0);
    assert(used == 5 && events[4].size == 1);
    events[4].size = 0xffffffff; h0_dma_stop(0x1000, 0);
    assert(dropped == 1 && events[4].size == 0xffffffff);
    while (used < 256) h0_event(1, 0, 0, 0);
    h0_dma_stop(0x1000, 0); assert(dropped == 2 && used == 256);
    active=0; h0_dma_stop(0x1000, 0); assert(dropped == 2);
    used=dropped=0; active=1; summarize_dma=0;
    h0_dma_stop(0x1000, 0); h0_dma_stop(0x1000, 0);
    assert(used == 2 && events[0].kind == 6);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.c').write_text(harness)
            subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(Path(__file__).resolve().parents[2]/'diagnostics/tinyspl'),
                            str(root/'test.c'), '-o', str(root/'test.exe')], check=True, capture_output=True)
            subprocess.run([str(root/'test.exe')], check=True, capture_output=True)
