# Development rules

Implement only the P0 and D13x Z0 scope. Keep reference SDK and Zephyr trees
read-only; use an isolated tree and documented patches for core changes.
Do not infer hardware parameters, copy another runtime, flash, push or publish.
Keep user-owned product changes intact. Never store access tokens.
Use Apache-2.0 for original code and retain third-party licensing.
Record copied, derived and reference-only sources in docs/provenance.yml.
Use tests.yaml for Twister metadata at the pinned Zephyr revision.
Distinguish QEMU runtime, target build and physical hardware validation.
Never invent a human identity or Signed-off-by. Human DCO review is pending.
Scripts must return a nonzero status on failures. Do not suppress failed tests.
