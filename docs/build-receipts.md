# Controlled candidates and evidence transport

Commit the module before delivery builds. Run scripts/build_candidate.py
separately for bringup, kernel and fpu, each with a new short build path.
The builder refuses existing directories, dirty module sources and undeclared
Zephyr changes. The isolated Zephyr tree may contain exactly the verified patch
series. It checks source/dependency identity before and after the successful build
and writes build-provenance.json only after validating the actual generated
application, board, module consumer, tool paths and ELF-to-bin command.

The receipt records all tracked module file hashes, a runtime source inventory,
the build command and paths, pinned dependency and patch identities, compiler/ar/
objcopy versions and file hashes, actual binary conversion options, selected link
input hashes, and final ELF/bin/map/config/DTS/build metadata hashes. Receipts are
integrity records, not cryptographic signatures or a malicious-host attestation.
The build and linked input files must remain available for collection.

package_candidate.py requires the receipt. It rejects old firmware after a
runtime source or patch change, a foreign module/application/board, absent or
modified payloads, changed tools or link inputs, and a failed Git identity read.
Documentation/collector changes can legitimately postdate the firmware:
source_at_build always retains the builder's identity; collector_at_package
records the collector's current identity. Runtime file hashes still must match.
Do not fabricate a receipt for an old build. Rebuild it through the controlled path.

The collector replays the generated objcopy options into a temporary file and
compares the raw bin byte for byte. It requires an identity-mapped, file-backed,
two-byte-aligned RV32C executable entry. It reads actual GNU map archive inclusion
and direct LOAD entries, retains paths containing spaces and audits every selected
member, including archives inside the build tree. CMAKE_AR comes from the build
cache. Missing, duplicate or unsupported members/maps fail closed. Unlinked object
files are not substituted for selected archive members.

## Runtime gates

Twister runs the three original scenarios, assertions-off bringup, and three
fake-MMIO CLIC variants. The CLIC tests include the actual patched driver; the
injected device/MMIO/CSR layer is not an E907 hardware model. Initial invalid-width
failures are retained, together with the narrow follow-up guard patch. Tests cover
cfg/info/threshold layout, widths 0..8, rejection of 9..15, zero level bits,
level clamping, first/last valid IRQ slots, enable/pending/SHV and generic/Nuclei
valid encoding. PMP/CSR/trap/mret hardware behavior remains outside this injection.

Run scripts/runtime_probes.py with a new output directory and --sdk pointing to
the installed SDK. The assertions-off worker fault must produce a nonzero Twister
result, its explicit failure message, and no bringup PASS. A paused QEMU guest
must reach the independent three-second host watchdog and return code 124. These
are successful negative probes of failed guest executions, not extra target passes.
The wrapper retains failed logs and terminates the child process tree on timeout.

FPU spin limits count assembly iterations rather than elapsed time. The default
remains 5,000,000; CONFIG_AIC_FPU_PEER_SPIN_LIMIT exposes it and the runtime log prints
the value. A 120-second target deadline does not replace Twister's independent
180-second host timeout. Different CPU frequencies require observed results and
reviewed limits, not a portable-time interpretation of that iteration count.

## Evidence ZIP

The Windows workflow stages a single ZIP from explicit QEMU, D13x, negative-probe,
candidate and dedicated log roots. It does not traverse the workspace. Successful
staging requires all three schema-2 candidates and passing gate reports. It checks
each candidate's exact allowlist, size and SHA-256. The ZIP explicitly includes
.config; upload-artifact's hidden-file default no longer determines its presence.
Failure/cancelled staging retains available logs and a failed status without a
candidate success index. No continue-on-error is used.

evidence.json indexes bringup/kernel/FPU source commits, individual ELF hashes,
expected output and pending hardware status. It inventories every archived file
except itself, avoiding a self-hash cycle. CI uploads only that ZIP, downloads the
artifact into a separate directory, then runs scripts/evidence.py verify on the
downloaded file. Verification rejects extra/missing/duplicate entries, unsafe
paths, changed sizes/hashes and missing candidate .config files.

Both staging and downloaded-archive verification require the exact pinned test
inventory: seven QEMU configurations / 23 executed cases, and three D13x
configurations / seven build-only cases. Platform identity, unique scenarios,
unique case identifiers and execution status are checked. The optional filtered
D13x assertions-off scenario is not execution. A renamed, omitted or added test
requires an intentional acceptance-inventory update; scenario names alone cannot
stand in for complete coverage.

Download verification also rechecks archived environment/negative-probe results
and binds each index entry to its own candidate application, source commit, ELF
digest and pending-hardware scope. All three source commits must agree. Rehashing
an internally contradictory report does not make it pass. This is consistency
validation, not cryptographic authentication of the producer or hardware evidence.

Local archive roundtrips do not prove GitHub transport. A new remote Windows run
requires separate push authorization. Linux clean-workspace initialization,
build and collection remain a prerequisite before a cross-platform delivery
claim; native Windows success alone does not establish that result.

The H0 handoff_probe application also uses the controlled receipt path and a
separate build-only tests.yaml. It is not added to the original R1 runtime
acceptance inventory. See bringup/d13x-h0-closure.md for its current source binding.
