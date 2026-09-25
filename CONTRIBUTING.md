# Contributing

Original code is Apache-2.0. Preserve third-party license and copyright notices;
record sources and original hashes in `docs/provenance.yml`. Review status means
the declared file-level license and transformation were checked; automated tests
are not legal review or DCO certification.

Run `python scripts/check_provenance.py` and
`python -m unittest discover -s tests/host -v`, followed by the QEMU and D13x
build/runtime checks documented in README.md. Do not hide failures or count
build-only tests as runtime passes.

Use narrow, coherent commits. Never stage build outputs, SDK files, tokens or
virtual environments. Local commits may remain `human_signoff_pending` until a
human reviews and signs; an agent must not sign on their behalf. Do not change
global Git settings. No automatic publishing or hardware flashing.
