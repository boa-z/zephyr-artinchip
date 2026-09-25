# Upstream policy

This is community-maintained downstream work, not official ArtInChip or Zephyr
board support. `boa` is a local board vendor namespace. Vendor prefixes and
board sponsorship require review before an upstream submission.

No push, pull request, issue, release, tag, flash, partition change or bootloader
replacement is part of the local workflow. Human sign-off remains pending.
Never generate a Signed-off-by or infer a real name from a GitHub login.
Record AI assistance accurately using Assisted-by when creating commits.

If core hooks are insufficient, use a separate staging worktree based on the
pinned SHA. Document each prerequisite, base, purpose, tests, removal condition
and `git apply --check` result. Keep normal dependencies and staging separate;
never claim an unpatched upstream baseline when patches are in use.

Candidate order: generic architecture prerequisites, minimal SoC/driver/board
consumers, then independently testable peripherals. Upstream preparation must
include philosophers and applicable kernel tests with only submitted inputs.
After upstream acceptance update the pinned dependency and remove duplicate
downstream implementations together.
