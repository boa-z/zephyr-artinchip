# SPDX-License-Identifier: Apache-2.0
"""Emit bounded loader memory evidence; unresolved ownership returns exit 2."""
import argparse
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from elftools.elf.elffile import ELFFile
from audit_loader import loader_layout, overlaps
from evidence import record


# Reviewable source trace, not a C interpreter or source-to-binary attestation.
TRACE = [
    ("NAND OS dispatch", "application/baremetal/bootloader/cmd/nand_boot.c", "spl_load_simple_fit", "do_nand_boot"),
    ("FIT external read and CRC", "application/baremetal/bootloader/lib/fitimage/fitimage.c", "reserve_size =", "spl_load_fit_image"),
    ("FIT header/tree allocation", "application/baremetal/bootloader/lib/fitimage/fitimage.c", "header = aicos_malloc", "spl_load_simple_fit"),
    ("MTD partition read", "bsp/artinchip/drv_bare/spinand/spinand_mtd.c", "spinand_read(flash", "mtd_spinand_read"),
    ("NAND page bounce", "bsp/peripheral/spinand/spinand.c", "buf = malloc(flash", "spinand_read"),
    ("NAND persistent aligned page", "bsp/peripheral/spinand/spinand.c", "flash->databuf = aicos_malloc_align", "spinand_init"),
    ("QSPI receive", "bsp/artinchip/drv_bare/spinand/spinand_port.c", "static u32 aic_qspi_receive", "aic_qspi_receive"),
    ("QSPI DMA stop and cache", "bsp/artinchip/hal/qspi/hal_qspi_v1x.c", "qspi_master_transfer_dma_sync", "qspi_master_transfer_dma_sync"),
    ("DMA task pool", "bsp/artinchip/hal/dma/hal_dma_def_v1x.c", "aich_dma.freetask = NULL", "hal_dma_init"),
    ("Allocator regions", "bsp/artinchip/drv_bare/umm_heap/malloc_port.c", "heap_def_t heap_def", "heap_init"),
    ("OSAL allocation adapter", "kernel/common/include/osal/aic_osal_baremetal.h", "return aic_tlsf_malloc", None),
    ("boot arguments and cache/IRQ handoff", "application/baremetal/bootloader/lib/common/boot_app.c", "aicos_dcache_clean", "boot_app"),
    ("optional config DTB", "packages/artinchip/of/of.c", "of_fdt_dt_init_bare_nornand", "of_fdt_dt_init_bare_nornand"),
    ("RAM FIT copy", "application/baremetal/bootloader/cmd/ram_boot.c", "CONFIG_LPKG_USING_FDTLIB", "do_ram_boot"),
    ("CPU initialization", "bsp/artinchip/sys/d13x/system.c", "void SystemInit", "SystemInit"),
    ("Requested loader config", "target/configs/d13x_d50t-2-lite_baremetal_bootloader_defconfig", "CONFIG_AIC_USING_DMA", None),
]


def route_requirements(route):
    if route not in {"all", "nand-fit"}:
        raise ValueError("unsupported boot route")
    result = ["No reproduced source/config-to-loader build receipt; current source can differ from linked object.",
              "Reserved heap consumers, PBP state, active display/USB/DMA and SRAM aliases not fully bounded.",
              "Recovery after an unbootable application is not verified."]
    if route == "all":
        result.append("RAM-only staging and compatible RAM FIT executor are not verified.")
    return result


def analyze(sdk, audit_path, objdump, route="all"):
    blockers = route_requirements(route)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["audit_status"] != "PASS" or not audit["loader_comparison"]["exact_match"]:
        raise ValueError("matching loader static audit required")
    inputs = audit["input_files"]
    for name, expected in inputs.items():
        if record(Path(name).read_bytes()) != expected:
            raise ValueError("loader audit input changed: " + name)
    elf_path = next(Path(n) for n in inputs if n.endswith("d13x.elf"))
    elf_data = elf_path.read_bytes()
    map_path = elf_path.with_suffix(".map")
    map_text = map_path.read_text(encoding="utf-8")
    _, _, _, spans = loader_layout(elf_data, elf_path.with_suffix(".bin").read_bytes())
    elf = ELFFile(io.BytesIO(elf_data))
    symbols = {s.name: {"start": s["st_value"], "size": s["st_size"]}
               for s in elf.get_section_by_name(".symtab").iter_symbols() if s["st_value"]}
    map_bindings = {}
    for name in ("g_base_irqstack", "g_top_irqstack", "g_base_normalstack",
                 "g_top_normalstack", "heap_def", "boot_app", "spl_load_fit_image"):
        matches = re.findall(r"^\s*(0x[0-9a-fA-F]+)\s+" + name + r"\s*$", map_text, re.M)
        if len(matches) != 1 or int(matches[0], 16) != symbols[name]["start"]:
            raise ValueError("loader map/ELF symbol mismatch: " + name)
        map_bindings[name] = symbols[name]["start"]
    trace = []
    for name, path, marker, symbol in TRACE:
        source = sdk / path
        lines = source.read_text(encoding="utf-8").splitlines()
        hits = [i + 1 for i, line in enumerate(lines) if marker in line]
        if not hits:
            raise ValueError("source profile changed: " + path)
        trace.append({"name": name, "path": path, **record(source.read_bytes()),
                      "lines": hits, "symbol": symbol, "linked_symbol": symbols.get(symbol),
                      "confidence": "working-source-reference; symbol presence is not code equivalence"})
    candidate_spans = [span for c in audit["candidates"].values() for span in c["load_spans"]]
    regions = []

    def region(name, start, end, rule, lifetime, evidence, kind, rw, confidence):
        overlap = (overlaps(candidate_spans, [{"start": start, "end": end}])
                   if start is not None and end is not None else None)
        regions.append({"name": name, "start": start, "end": end, "allocation_rule": rule,
                        "lifetime": lifetime, "source_evidence": evidence, "kind": kind,
                        "reader_writer": rw, "candidate_overlap": overlap,
                        "confidence": confidence})

    for span in spans:
        region(span["name"], span["start"], span["end"], "ELF PT_LOAD or linker symbols",
               "loader entry through payload jump", [str(elf_path)], "static", "loader CPU",
               "ELF-bound; runtime aliasing unverified")
    for base, top in (("g_base_irqstack", "g_top_irqstack"), ("g_base_normalstack", "g_top_normalstack")):
        start, end = symbols[base]["start"], symbols[top]["start"]
        if base not in map_text or top not in map_text:
            raise ValueError("map missing stack symbols")
        region(base, start, end, "ELF stack symbols", "loader/IRQ calls until jump",
               [str(elf_path), str(map_path)], "static", "CPU/interrupts", "extent known; peak usage unknown")
    heap = spans[1]
    dynamic = [
        ("FIT header", "ALIGN_UP(sizeof(fdt_header), info.bl_len)", "spl_load_simple_fit entry to __exit_header", 2),
        ("FIT tree", "ALIGN_UP(fdt_totalsize,4); SPI-NAND does not use MMC rounding", "FIT parse to __exit", 2),
        ("SPI-NAND per-read bounce", "page_size + oob_size via malloc", "spinand_read to exit/free", 4),
        ("SPI-NAND persistent page/OOB", "page_size + oob_size aligned to CACHE_LINE_SIZE", "spinand_init onward", 5),
    ]
    for name, rule, lifetime, index in dynamic:
        region(name, heap["start"], heap["end"], "subset of MEM_DEFAULT: " + rule, lifetime,
               [trace[index], trace[9], trace[10]], "dynamic", "CPU and QSPI DMA",
               "source-derived allocation envelope; no peak proof")
    for name in ("aich_dma", "g_dma_w_sync_buffer", "heap_def", "boot_arg", "g_aic_initial_blob"):
        sym = symbols.get(name)
        if sym:
            region(name, sym["start"], sym["start"] + sym["size"], "ELF object extent", "loader lifetime",
                   [str(elf_path)], "static", "CPU/DMA", "ELF-bound object")
    # Decode the linked ILP32 heap_def_t table, not today's Kconfig defaults.
    table = elf.get_section_by_name(".symtab").get_symbol_by_name("heap_def")[0]
    section = elf.get_section(table["st_shndx"])
    offset = table["st_value"] - section["sh_addr"]
    raw = section.data()[offset:offset + table["st_size"]]
    if len(raw) != table["st_size"] or not raw or len(raw) % 16:
        raise ValueError("unsupported linked heap_def table")
    heap_records = []
    for index, (name_ptr, mem_type, start, end) in enumerate(struct.iter_unpack("<4I", raw)):
        heap_records.append({"index": index, "name_pointer": name_ptr, "type": mem_type,
                             "start": start, "end": end})
        if start == end == 0:
            continue
        if start >= end:
            raise ValueError("invalid linked heap region")
        region("linked heap region " + str(index), start, end, "heap_def_t extracted from ELF initialized data",
               "heap_init through payload jump", [str(elf_path)], "dynamic", "CPU and allocation consumers",
               "ELF-bound envelope; consumers and peak usage separately reviewed")
    disassembly = {}
    for name in ("do_ram_boot", "boot_app", "SystemInit", "aic_get_time_us", "heap_init",
                 "aic_get_boot_args", "of_fdt_dt_init_bare_nornand", "spl_load_fit_image",
                 "spl_load_simple_fit", "exec_cmd_write_input_data", "hal_dma_init",
                 "hal_dma_chan_stop", "hal_qspi_master_transfer_sync", "save_boot_params"):
        disassembly[name] = subprocess.check_output(
            [str(objdump), "-d", "--disassemble=" + name, str(elf_path)], text=True)
        if "<" + name + ">:" not in disassembly[name]:
            raise ValueError("required linked function missing: " + name)
    # Reset_Handler's symbol extent only covers its first jump. Include the
    # continuation up to __exit rather than silently omitting startup code.
    begin, end = symbols["Reset_Handler"]["start"], symbols["__exit"]["start"]
    if not begin < end or end - begin > 4096:
        raise ValueError("unexpected startup span; manual review required")
    disassembly["startup_to_exit"] = subprocess.check_output(
        [str(objdump), "-d", "--start-address=" + hex(begin),
         "--stop-address=" + hex(end), str(elf_path)], text=True)
    for app, candidate in audit["candidates"].items():
        file_spans = candidate.get("file_spans", [])
        if not file_spans:
            raise ValueError("current audit with file spans required")
        region(app + " FIT destination", min(s["start"] for s in file_spans),
               max(s["end"] for s in file_spans), "FIT external data directly to verified load; no compression/cipher",
               "spl_read through payload execution", [trace[1], trace[3], trace[4]], "dynamic",
               "CPU/QSPI DMA writes, CRC reads, payload executes", "intentional candidate overlap")
    unresolved = [
        ("loader display/USB live state", "heap envelopes extracted, but active bus masters and consumers need closure", [trace[9], trace[15]]),
        ("PBP/TCM/aliases and inherited DMA", "not bounded by tinySPL PT_LOAD; installed hardware mapping and bus masters unknown", [trace[14]]),
        ("optional config DTB", "fixed PSRAM tail destination when config partition exists; DTB-derived size lacks complete range proof. Current user log reports No config partition", [trace[12]]),
    ]
    if route == "all":
        unresolved.append(("RAM-only FIT staging", "no approved address or compatible RAM FIT executor", [trace[13]]))
    for name, rule, evidence in unresolved:
        region(name, None, None, rule, "potentially live through jump", evidence, "dynamic",
               "loader/PBP/peripherals", "unresolved")
    return {"schema_version": 1, "status": "BLOCKED", "boot_route": route,
            "ram_only_staging_required": route != "nand-fit",
            "route_limits": "nand-fit excludes only host RAM staging; NAND page buffers, DMA and recovery remain in scope",
            "static_memory_overlap": audit["static_memory_overlap"],
            "ram_ownership": "unverified", "loadable_image": False, "hardware_validation": "pending",
            "input_files": {**inputs, str(map_path): record(map_path.read_bytes())},
            "candidate_bindings": audit["candidates"], "trace": trace, "regions": regions,
            "linked_heap_table": heap_records, "linked_disassembly": disassembly,
            "map_elf_symbol_bindings": map_bindings,
            "disassembler": {"path": str(objdump), **record(objdump.read_bytes())},
            "cpu_handoff": {"source_sequence": ["dcache clean", "icache invalidate", "local IRQ disable", "ep(dev, boot_arg)"],
                            "unknown": ["other bus masters quiesced", "cache/map/TCM runtime state", "exact compiled-source/config receipt", "stack high water"],
                            "probe": "stackless entry before Zephyr __start; no CSR writes; FS-guarded fcsr"},
            "candidate_window_answer": "Cannot exclude every live-buffer/alias overwrite of [0x30080000,0x30100000). Known default-heap envelopes are disjoint; payload writes intentionally target SRAM.",
            "blockers": blockers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--route", choices=["all", "nand-fit"], default="all")
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.sdk.resolve()):
        raise ValueError("new output outside read-only SDK required")
    result = analyze(args.sdk, args.audit, args.objdump, args.route)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "blockers": result["blockers"]}))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
