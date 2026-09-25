# Z0.R1 software evidence and Z0.H0 handoff

## Remote acceptance follow-up: 2026-09-25

The results in this section supersede the remote-pending statements in the
original local-delivery snapshot below; that historical evidence is retained.

Run 36099116552 at a6073105d8de0d636de51e1f75d8e84aebce85f4 completed SUCCESS.
The complete Windows workflow passed: bootstrap, host gates, SDK installation,
QEMU, negative runtime probes, D13x builds, candidate collection, evidence ZIP
upload, download and verification. A separate local download at
artifacts/ci-36099116552/software-evidence.zip passed the strengthened verifier
from 480e95e: 99 files, seven QEMU configurations / 23 passed cases, three D13x
configurations / seven build-only cases, zero physical-board runtime passes.
All three candidate .config files are present in the downloaded ZIP.

This closes the R1/R2 Windows success-path transport gap for that source commit.
The earlier run 36096131063 remains the separate failure-path transport evidence.
The three downloaded candidate source_at_build values all equal a607310; each
candidate keeps its own ELF hash and receipt. This is a new software build, not
a relabeling of the historical f2ce05e candidates.

Commit 480e95e additionally rejects duplicate scenarios, wrong platforms, missing
or duplicate cases, rehashed contradictory gate reports and candidate-index
misbinding. Local validation: 82 host tests, lint and provenance PASS; both the
historical success ZIP and failure ZIP verify. Removing one case from the actual
historical QEMU report and recomputing its archive hash still returns CLI exit 1.
Receipt: artifacts/r1-evidence-semantics/real-archive-negative.json. Its own remote
run 36099414248 at 480e95ed7844574e33fd389f85d8d3133ef9a000 completed SUCCESS
on 2026-09-25 at 05:48:22 UTC. This status was rechecked through the GitHub CLI.
The downloaded archive contains 99 files and all three .config files; QEMU has
seven configurations / 23 passed cases, while D13x has three configurations /
seven build-only cases. All three candidate receipts identify 480e95e.
Archive SHA-256: 3c819d8a8b5810277f50f39e7c68ad8b72210440001d21495ee9aa78822115ee.

### Local receipt consistency follow-up

The next local change closes a reproduced acceptance gap: candidate manifests
and the index could agree on a relabeled source commit while contradicting the
unchanged build receipt. Likewise, replacing a payload and updating only the
collection/archive hashes was accepted. The real 480e95e archive reproduced
the source-identity gap before the fix.

Staging and download verification now require a successful, clean D13x build
receipt and matching application, board, full source snapshot, dependency
snapshot and binary conversion command. ELF, bin, map, .config, DTS and compile
commands must match the receipt's build-time hashes. These are offline
consistency checks: no receipt command is executed or machine-local build path
accessed. Receipts and SHA-256 hashes do not establish publisher authenticity.

Validation: 87 host tests PASS, lint PASS and provenance PASS. New regressions
failed before the implementation and pass after it. Historical failure archive
36096131063 and success archives 36099116552 / 36099414248 still verify; verifying
transport of a failure archive does not turn its software_audit into a pass.
Two altered copies of the real 480e95e archive, with recomputed manifest hashes,
now return CLI exit 1 for relabeled source identity and a replaced kernel bin.
Logs, archive hashes, candidate ELF hashes and negative results are retained in
artifacts/r1-receipt-consistency/host-tests.log and verification.json.

Reproduce the local gates with the project virtual environment:

```sh
python -m unittest discover -s tests/host -v
python scripts/lint.py
python scripts/check_provenance.py
python scripts/evidence.py verify artifacts/ci-36099414248/software-evidence.zip
```

This receipt-verifier change has local validation only; the completed remote
run belongs to 480e95e and predates this change. No new firmware build, QEMU
execution, physical-board run or push was performed in this follow-up.

Hardware remains pending, H0 remains BLOCKED, loadable_image remains false and
upstream_ready remains no. Linux independent clean-workspace validation remains
NOT_RUN; WSL is unavailable on this host and no Docker command was found.
No SDK/product source, reference Zephyr tree or physical board was modified.

## Original local-delivery snapshot

Date: 2026-09-25. Review baseline: b7c2525b34e585d942e2e2e8691e3d22e38945c2.
Scope remains P0 and D13x Z0. No physical board operation, push, merge, tag or
release was performed in this stage. Human ownership/license and DCO review
remain pending; no human Signed-off-by has been added.

## Resolved findings

| Finding | Implementation | Local evidence / remaining acceptance |
|---|---|---|
| R1 cross-drive upload | Stage one ZIP from explicit allowlisted roots; upload and download that ZIP; verify downloaded inventory, sizes and hashes. Preserve bootstrap/build/test logs on failure. | Local copied ZIP verified; intentional early bootstrap exit 23 preserved a failure-only archive. New GitHub run pending authorization. |
| R2 hidden config | ZIP explicitly includes all three candidate .config files. | Three configs present after local copy and verification; actual GitHub download remains pending. |
| R3 source identity | Controlled clean builds issue receipts with source/dependency/tool/input/output identities; collection validates receipt and keeps source_at_build separate from collector_at_package. | Missing/stale/foreign/tampered inputs rejected; actual pre-R1 build without receipt rejected with exit 1. |
| R4 assertions | Synchronization and timing execute outside assertions, with an explicit fatal/harness failure path. | Assert-on and assert-off QEMU pass; missing worker signal fails without PASS; host watchdog rejects a paused guest. |
| R5 payload consistency | Replay actual recorded objcopy command; compare bin bytes; require file-backed aligned entry and valid load segments. | Real changed/truncated bin, zero-fill/misaligned entry and truncated ELF rejected. |
| R6 linked inputs | Parse GNU map archive inclusion/direct LOAD entries, retain spaces, use recorded CMAKE_AR and inspect selected members even inside build. | Host tests cover spaces, relative paths, CRLF, missing/unsupported entries and local precompiled archives; all three actual link inventories audited. |
| R7 CLIC behavior | Compile actual patched driver with fake MMIO/device/CSR in legacy, generic and Nuclei variants. Add narrow invalid-width guard patch. | 15 register-layer cases pass. E907 CSR/trap/mret and physical interrupt behavior remain unverified. |

Implementation commits: 552e373 (assertion-independent bringup), e5968c9 (CLIC
regression and width guard), f2ce05e (receipts, payload audits and transport).
A follow-up CI change retains early bootstrap/SDK/gate transcripts. Firmware was
not rebuilt for subsequent documentation and workflow-only changes: the receipt
runtime inventory must still match, while collection records its newer identity.

## Test and negative evidence

Environment: Windows, Python 3.13.15, west 1.5.0, CMake 4.4.3, Ninja 1.13.2,
Zephyr SDK 1.0.1 / GCC 14.3.0, QEMU 10.0.2. Environment record:
artifacts/r1-environment.json. Raw logs: artifacts/logs/r1-*.log.

| Gate | Result | Evidence |
|---|---|---|
| Host regressions | 53 passed | artifacts/logs/r1-host-tests-final.log |
| Final QEMU | 7 configurations / 23 cases passed; 0 filtered, failed or errored; 126.01 s | C:/tmp/aic-r1-qemu-final/twister.json and handler logs |
| Final D13x Twister | 3 build-only configurations; 1 static filter for QEMU-only no_assert; 0 target runtime passes | C:/tmp/aic-r1-d13x-final/twister.json |
| Separate delivery builds | bringup, kernel and fpu each built and audited with a receipt | C:/tmp/aic-r1-bringup, C:/tmp/aic-r1-kernel, C:/tmp/aic-r1-fpu |
| Worker fault | Twister exit 1, explicit failure, no bringup PASS | C:/tmp/aic-r1-negative/missing-signal and probes.json |
| Paused CPU | Host monotonic watchdog, exit 124, timed_out=true after about 3.31 s | C:/tmp/aic-r1-negative/probes.json |
| Actual payload corruption | All six invalid cases rejected | artifacts/logs/r1-real-negative-probes.log |
| Local archive transport | Success and failure copies verified; success contains 3 hidden configs, failure has no candidate index | artifacts/logs/r1-local-transport.log |
| Early failure | Child PowerShell exit 23 retained bootstrap transcript; log-only ZIP verified | artifacts/r1-early-failure/failure-evidence.zip |

FPU final QEMU log reports peer limit 5,000,000 assembly iterations, 120 s target
deadline, 5,003 + 5,004 preemption checks and 200 voluntary checks. Twister has
an independent 180 s host timeout. The iteration count is configurable and is
not a duration or evidence of a suitable real-board clock-dependent limit.

The CLIC pre-guard run is retained at C:/tmp/aic-r1-clic-before and
artifacts/logs/r1-clic-before.log. Its failures included invalid control widths
and a test-fixture PMP CSR counting issue. The fixture now explicitly excludes
PMP and the real driver rejects widths above eight before encoding. Passing the
fake-MMIO suite does not establish E907 PMP/CSR/exception return behavior.

Host negative coverage includes changed runtime source or patch, foreign module,
missing receipt, changed config/ELF/map/bin, failed Git identity read, linked
archive edge cases, missing hidden config, archive corruption and unsafe paths.
Real corruption probes use copies and preserve original successful builds.
These are expected failed executions counted as negative checks, not target passes.

Reproduction commands (new output directories are required):

~~~powershell
python scripts/lint.py
python scripts/check_provenance.py
python -m unittest discover -s tests/host -v
python scripts/apply_patches.py --check
west twister -p qemu_riscv32 -T samples/bringup -T tests/kernel -T tests/fpu -T tests/clic --board-root boards --outdir C:/tmp/aic-r1-qemu-final --inline-logs -j4
west twister -p d50t_2_lite/d133ecs -T samples/bringup -T tests/kernel -T tests/fpu --board-root boards --build-only --outdir C:/tmp/aic-r1-d13x-final --inline-logs -j3
python scripts/runtime_probes.py C:/tmp/aic-r1-negative --sdk "$env:ZEPHYR_SDK_INSTALL_DIR"
foreach ($app in @('bringup','kernel','fpu')) {
  python scripts/build_candidate.py $app "C:/tmp/aic-r1-$app"
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
  python scripts/package_candidate.py "C:/tmp/aic-r1-$app" "artifacts/r1-delivery/candidates/$app"
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
~~~

Run each gate separately and stop on any nonzero exit. Use fresh paths when
reproducing this report; do not erase or overwrite these evidence directories.

## Candidate identities and hashes

All three receipts identify clean firmware source
f2ce05eadfe690500b864b8eef0328d2000bbd24. Final collection is under
artifacts/r1-delivery/candidates/{bringup,kernel,fpu}; each directory contains
candidate.json plus 14 hashed payload/evidence files, including its own
build-provenance.json. The collector commit is recorded separately in each
manifest. ELF sizes below include debug data and are not SRAM usage.

| Application | ELF bytes | ELF SHA-256 | Linker RAM usage |
|---|---:|---|---:|
| bringup | 372468 | ffa6df9c739e6217ef13153e18442cfaeba367d0c316a8e1971bd7b310eecb38 | 34368 bytes |
| kernel | 591864 | 02268b43c24bbfa31c7f5ece938c5b416e785189e1341fe3da73b3f8d23a67e7 | 44480 bytes |
| fpu | 590212 | 6f78418d1e365dbe13165c9c247367a6452b6a469c8058361334728974115884 | 49456 bytes |

Audited selected archive members: 109 / 114 / 115 respectively, plus three direct
objects per application. Compile command counts: 119 / 124 / 125. The candidate
manifests retain detailed ELF spans, link inputs, conversion command and hashes.

The upper-level index is evidence.json in
artifacts/r1-delivery/software-evidence.zip, also extracted beside the ZIP for
inspection. It identifies each application, source, ELF hash, expected output
and pending hardware scope. It hashes all archived files except itself to avoid
a circular digest. Final local copied-archive verification is recorded separately
in artifacts/r1-delivery/local-transport-verification.json.

Zephyr remains pinned to 839728050444f90d06870b5fc9bbbda106d91459. Only the
isolated zephyr-upstream tree contains the exactly verified two-patch series:

- 0001-clic-legacy-mmio-layout.patch:
  d493c9797d801138ef5017f7bbfe418073bcd902e7cb08698dafe78fb9454339
- 0002-clic-validate-control-width.patch:
  39a8e07cd95372c6ad3089ac1fc134079b7301e0b355058825bfc734837aa15f

The second patch rejects impossible CTLBITS/NLBITS before shift encoding; the
series records all expected final Git blobs. The fixed SDK reference remains
c5807f9e7d18292f920dafaa018b8174635085c4. Original Zephyr and product/reference
trees are read-only and existing product modifications are preserved. Earlier
5ca65c6 artifacts and this stage's intermediate successes/failures are retained.

## Remote CI and transport status

The prior GitHub Actions run 36092052502 at b7c2525 was rechecked read-only:
bootstrap, host, QEMU and D13x steps passed; artifact upload failed because the
D: workspace root was not a parent of C: build logs. Overall conclusion: FAILURE.
Raw metadata/logs are artifacts/r1-remote-run.json and
artifacts/logs/r1-prior-remote-failure.log.

The revised workflow uploads one ZIP, downloads it and verifies its contents.
Local staging and copied-archive verification pass, including failure-only mode.
Actual new GitHub upload/download verification is NOT_RUN: this stage has no new
push authorization. R1/R2 remote acceptance therefore remains open. No workflow
is described as remotely green based on local results.

Status dimensions: software_audit=pass locally; local archive verification=pass;
transport_verified=pending for GitHub; hardware_validation=pending;
loadable_image=false; upstream_ready=no.

Linux independent clean-workspace validation is explicitly scheduled as a gate
before cross-platform/upstream advancement, currently NOT_RUN. In a separate
Linux x86_64 workspace: initialize pinned west sources, install/check the Linux
SDK, apply/audit the same patch series, run host and QEMU gates, build all three
D13x candidates, collect receipts and verify copied evidence. Retain Linux tool
versions and logs separately; do not assume the Windows package lock is portable.

## H0 remaining blockers

docs/bringup/d13x-handoff.yml is the machine-readable handoff record. Each item
is classified with evidence, required evidence and limitations. The pinned
ram_boot.c and boot_app.c inform reference load/jump semantics, but do not identify
the installed loader. The previously cited local loader ELF was absent during
this check; that observation says nothing about the board's installed image.

H0 remains BLOCKED on actual PCB/part/startup/recovery identity; installed loader
and accepted container/signature; loader code/stack/heap/staging/DMA/temporary RAM
ownership throughout loading; CPU/CSR/cache/trap handoff; actual UART route,
electrical levels and clock; power hold; timer/CLIC measurements; and human
operator authorization. No staging address or load command has been selected.
The 512 KiB link allocation is diagnostic and is not proven-free physical RAM.

H1 cold starts, warm/RAM reloads, ten-minute kernel/FPU hardware sessions,
independent clock measurement, exception recovery and PC/serial capture are
NOT_RUN. PSRAM, cache maintenance, DMA/display coherency and additional Z1
peripherals are outside this software evidence. Missing hardware evidence is
left explicit rather than replaced by more simulated passes.
