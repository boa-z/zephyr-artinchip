# SPDX-License-Identifier: Apache-2.0
"""Gate packager: rejections, the unpinned override and baseline identity."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import package_gate_trial as gate
from evidence import record

REFERENCE = b"d133-product-image-fixture"
STRESS_ELF = b"stress-elf-fixture"
STRESS_BIN = b"stress-bin-fixture"
KERNEL_ELF = b"kernel-elf-fixture"
KERNEL_BIN = b"kernel-bin-fixture"
FPU_ELF = b"fpu-elf-fixture"
FPU_BIN = b"fpu-bin-fixture"
PINS = {"stress": (record(STRESS_ELF)["sha256"], record(STRESS_BIN)["sha256"]),
        "kernel": (record(KERNEL_ELF)["sha256"], record(KERNEL_BIN)["sha256"]),
        "fpu": (record(FPU_ELF)["sha256"], record(FPU_BIN)["sha256"])}


def stress_config(duration="600", inject=None):
    lines = [f"CONFIG_AIC_Z0_STRESS_DURATION_SEC={duration}",
             "CONFIG_AIC_Z0_STRESS_HEARTBEAT_SEC=5"]
    for symbol in gate.INJECTABLE:
        enabled = inject is not None and symbol == f"CONFIG_AIC_Z0_STRESS_INJECT_{inject.upper()}"
        lines.append(f"{symbol}=y" if enabled else f"# {symbol} is not set")
    return "\n".join(lines) + "\n"


class GatePackagingTests(unittest.TestCase):
    def package(self, elf=STRESS_ELF, raw=STRESS_BIN, app="stress", config=stress_config(),
                baseline=True):
        with patch.object(gate, "PINNED", PINS), patch.object(
                gate, "BASELINE", record(REFERENCE)["sha256"] if baseline else gate.BASELINE):
            return gate.package(REFERENCE, elf, raw, app=app, image_name="gate.img",
                                config_text=config)

    def test_hardware_profile_is_stated_explicitly(self):
        # A build that does not state its own duration is not evidence of 600 s.
        for config in (None, "", "CONFIG_AIC_Z0_STRESS_DURATION_SEC=600\n"
                       "CONFIG_AIC_Z0_STRESS_DURATION_SEC=600\n"):
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "profile"):
                self.package(config=config)

    def test_short_coverage_profile_cannot_be_a_hardware_image(self):
        for duration in ("2", "3", "5", "599"):
            with self.subTest(duration=duration), self.assertRaisesRegex(
                    ValueError, "coverage profile"):
                self.package(config=stress_config(duration=duration))

    def test_fault_injection_build_is_never_packaged(self):
        for mode in ("mil", "fpu", "timer", "peer"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, "fault injection enabled"):
                self.package(config=stress_config(inject=mode))

    def test_tampered_stress_bin_is_rejected(self):
        for raw in (STRESS_BIN[:-1], STRESS_BIN + b"X", b"stress-bix-fixture"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "BIN differs"):
                self.package(raw=raw)

    def test_tampered_stress_elf_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ELF differs"):
            self.package(elf=STRESS_ELF + b"X")

    def test_cross_application_mix_is_rejected(self):
        # Each pin is keyed by --app, so another gate build cannot ride along.
        with self.assertRaisesRegex(ValueError, "stress ELF differs"):
            self.package(elf=KERNEL_ELF, raw=KERNEL_BIN)
        with self.assertRaisesRegex(ValueError, "kernel ELF differs"):
            self.package(elf=STRESS_ELF, raw=STRESS_BIN, app="kernel")
        with self.assertRaisesRegex(ValueError, "unknown gate app"):
            self.package(app="bringup")

    def test_wrong_product_baseline_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "pinned known-good"):
            self.package(baseline=False)

    def test_allow_unpinned_overrides_the_pin_and_labels_the_record(self):
        # A new source revision must be packageable without faking the reviewed pin.
        with patch.object(gate, "PINNED", PINS), patch.object(
                gate, "BASELINE", record(REFERENCE)["sha256"]), patch.object(
                gate, "window_binding", return_value=({"p_memsz": 4096}, 0x40000000)), patch.object(
                gate, "encode", return_value=b"fit"), patch.object(gate, "verify"), patch.object(
                gate, "replace_os", return_value=b"image"), patch.object(
                gate, "verify_replacement", return_value={}):
            _, _, report = gate.package(REFERENCE, b"new-kernel-elf", b"new-kernel-bin",
                                        app="kernel", image_name="gate.img",
                                        allow_unpinned=True)
        self.assertTrue(report["unreviewed_build"])
        self.assertEqual(report["status"], "OFFLINE_VERIFIED_UNPINNED")
        self.assertNotIn("re-checks the pinned", report["limits"])
        self.assertIn("no board result applies", report["limits"])
        with patch.object(gate, "PINNED", PINS), patch.object(
                gate, "BASELINE", record(REFERENCE)["sha256"]), self.assertRaisesRegex(
                ValueError, "kernel ELF differs"):
            gate.package(REFERENCE, b"new-kernel-elf", b"new-kernel-bin",
                         app="kernel", image_name="gate.img")


if __name__ == "__main__":
    unittest.main()
