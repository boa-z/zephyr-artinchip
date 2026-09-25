# SPDX-License-Identifier: Apache-2.0
"""Apply reviewed observation hooks to a disposable SDK copy, never its reference."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import sys

from evidence import record

ROOT = Path(__file__).resolve().parents[1]
FIT = "application/baremetal/bootloader/lib/fitimage/fitimage.c"
BOOT = "application/baremetal/bootloader/lib/common/boot_app.c"
SPI = "bsp/peripheral/spinand/spinand.c"
QSPI = "bsp/artinchip/hal/qspi/hal_qspi_v1x.c"


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("source context changed: " + old[:70])
    return text.replace(old, new)


def changes(path, text, observe_only=False, transfer_only=False):
    if observe_only and transfer_only:
        raise ValueError("observation and transfer modes are mutually exclusive")
    original = text
    text = '#include <h0_diag.h>\n' + text
    if path == FIT:
        text = once(text, "    u8 *p = buf;", "    u8 *p = buf;\n    h0_event(1, (uintptr_t)buf, size, offset);")
        text = once(text, "    return rdlen;", "    h0_event(2, (uintptr_t)buf, size, (uint32_t)rdlen);\n    return rdlen;")
        text = once(text, "    if (!size)\n        return size;",
                    "    if (!size) {\n        h0_event(2, (uintptr_t)buf, size, 0);\n        return size;\n    }")
        text = once(text, "        if (offset == UINT32_MAX)\n            return -1;",
                    "        if (offset == UINT32_MAX) {\n            h0_event(2, (uintptr_t)buf, size, (uint32_t)-1);\n            return -1;\n        }")
        text = once(text, "            ret = spl_read(info, offset, (u8 *)load_addr, length);",
                    "            h0_state(2);\n            h0_event(3, load_addr, length, offset);\n            ret = spl_read(info, offset, (u8 *)load_addr, length);")
        signature = "int spl_load_simple_fit(struct spl_load_info *info, ulong *entry_point)\n{"
        text = once(text, signature, signature + "\n    h0_begin();")
        if observe_only:
            text = once(text, "    h0_begin();", "    h0_begin();\n    h0_dump(0);\n    printf(\"H0-OBSERVE-ONLY: OS not read; no payload jump; return to console\\n\");\n    return -1;")
        if transfer_only:
            text = once(text, "    h0_begin();", "    h0_begin_transfer();")
            text = once(text, "    h0_event(1, (uintptr_t)buf, size, offset);",
                        "    h0_event(1, (uintptr_t)buf, size, offset);\n"
                        "    if (info->dev_type != DEVICE_SPINAND ||\n"
                        "        !h0_read_allowed((uintptr_t)buf, size, offset)) {\n"
                        "        h0_event(9, (uintptr_t)buf, size, offset);\n"
                        "        h0_event(2, (uintptr_t)buf, size, (uint32_t)-1);\n"
                        "        return -1;\n    }")
            text = once(text, "            h0_state(2);",
                        "#ifndef LPKG_USING_FDTLIB_CRC32_VERIFY\n"
                        '#error "H0 transfer requires CRC verification"\n'
                        "#else\n"
                        "            if (crc1 != 0xf183bd17U) {\n"
                        "                h0_event(9, load_addr, length, crc1);\n"
                        "                return -1;\n            }\n"
                        "#endif\n            h0_state(2);")
            text = once(text, '                printf("CRC32 verify OK.\\n");',
                        '                h0_event(8, load_addr, length, crc2);\n                printf("CRC32 verify OK.\\n");')
            # Only the FIT loader's terminal return is replaced. Every cleanup
            # path converges here, including failures; no entry is dereferenced.
            text = once(text, "    aicos_free(MEM_DEFAULT, header);\n    return ret;",
                        "    aicos_free(MEM_DEFAULT, header);\n"
                        "    h0_event(7, 0, 0, (uint32_t)ret);\n"
                        "    h0_dump(0);\n"
                        "    printf(\"H0-TRANSFER-ONLY: FIT attempt ended; no payload jump; return to console\\n\");\n"
                        "    return -1;")
            text = once(text, '        printf("No space to malloc for header\\n");\n        return -1;',
                        '        printf("No space to malloc for header\\n");\n        ret = -1;\n        goto __exit_header;')
    elif path == BOOT:
        if transfer_only:
            text = once(text, "    aicos_dcache_clean();",
                        '    printf("H0-TRANSFER-ONLY: boot_app blocked\\n");\n    return;\n    aicos_dcache_clean();')
            return text
        text = once(text, "    aicos_dcache_clean();",
                    "    if (h0_dump((uintptr_t)ep)) {\n        printf(\"H0-SPL refusing jump: incomplete trace\\n\");\n        return;\n    }\n    aicos_dcache_clean();")
    elif path == SPI:
        line = "    buf = malloc(flash->info->page_size + flash->info->oob_size);"
        text = once(text, line, line + "\n    h0_event(4, (uintptr_t)buf, flash->info->page_size + flash->info->oob_size, 0);")
        text = once(text, "    if (buf)\n        free(buf);",
                    "    if (buf) {\n        h0_event(5, (uintptr_t)buf, 0, 0);\n        free(buf);\n    }")
    elif path == QSPI:
        text, count = re.subn(r"(?m)^(\s*)hal_dma_chan_stop\(([^;\n]+)\);$",
                             r"\1H0_DMA_STOP(\2);", text)
        if count != 11:
            raise ValueError("QSPI stop call inventory changed")
    else:
        raise ValueError("unsupported path")
    if text == original:
        raise ValueError("no changes")
    return text


def apply(reference, destination, evidence, observe_only=False, transfer_only=False):
    if observe_only and transfer_only:
        raise ValueError("observation and transfer modes are mutually exclusive")
    reference, destination = reference.resolve(), destination.resolve()
    if (destination == reference or destination.is_relative_to(reference)
            or reference.is_relative_to(destination)):
        raise ValueError("disjoint SDK copy required")
    if evidence.resolve().is_relative_to(reference):
        raise ValueError("evidence must be outside reference SDK")
    if 'CONFIG_PRJ_APP="bootloader"' not in (destination / ".config").read_text():
        raise ValueError("configure the disposable copy for bootloader first")
    # Preflight all inputs before mutation; no partial patch on profile mismatch.
    prepared, inputs = {}, {}
    for path in (FIT, BOOT, SPI, QSPI):
        if not (destination / path).resolve().is_relative_to(destination):
            raise ValueError("copy file resolves outside isolated SDK")
        raw = (reference / path).read_bytes()
        if (destination / path).read_bytes() != raw:
            raise ValueError("copy differs or already patched: " + path)
        inputs[path] = record(raw)
        prepared[path] = changes(path, raw.decode("utf-8").replace("\r\n", "\n"), observe_only, transfer_only)
    additions = {
        "bsp/common/include/h0_diag.h": ROOT / "diagnostics/tinyspl/h0_diag.h",
        "application/baremetal/bootloader/lib/common/h0_diag.c": ROOT / "diagnostics/tinyspl/h0_diag.c"}
    if any((destination / path).exists() for path in additions):
        raise ValueError("diagnostic files already exist")
    if any(not (destination / path).resolve().is_relative_to(destination) for path in additions):
        raise ValueError("diagnostic destination resolves outside isolated SDK")
    evidence.mkdir(parents=True, exist_ok=False)
    patch = []
    for path, content in prepared.items():
        before = (reference / path).read_text(encoding="utf-8")
        patch.extend(difflib.unified_diff(before.splitlines(True), content.splitlines(True),
                                        fromfile="a/" + path, tofile="b/" + path))
        (destination / path).write_text(content, encoding="utf-8", newline="\n")
    for path, source in additions.items():
        shutil.copyfile(source, destination / path)
        patch.extend(difflib.unified_diff([], source.read_text().splitlines(True),
                                        fromfile="/dev/null", tofile="b/" + path))
    (evidence / "diagnostic.patch").write_text("".join(patch), encoding="utf-8", newline="\n")
    report = {"reference": str(reference), "copy": str(destination), "inputs": inputs,
              "outputs": {path: record((destination / path).read_bytes())
                          for path in (*prepared, *additions)},
              "observe_only": observe_only,
              "transfer_only": transfer_only,
              "hardware_validation": "pending", "loadable_image": False}
    (evidence / "patch-inputs.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("reference", "copy", "evidence"):
        parser.add_argument("--" + key, type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--observe-only", action="store_true", help="Return before FIT header/payload reads")
    mode.add_argument("--transfer-only", action="store_true", help="Attempt FIT reads then return; block all boot_app jumps")
    args = parser.parse_args()
    try:
        apply(args.reference, args.copy, args.evidence, args.observe_only, args.transfer_only)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
    print(json.dumps({"status": "PASS", "scope": "isolated source patch only"}))
