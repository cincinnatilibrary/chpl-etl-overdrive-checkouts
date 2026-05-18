#!/usr/bin/env bash
# capture-fixture.sh — Copy an OverDrive ETL run dir from ils-reports
# into tests/fixtures/ for use as a test fixture.
#
# Fixtures are kept LOCAL-ONLY (tests/fixtures/ is gitignored) because the
# captured pages contain per-checkout patron-linked userIds. Decision:
# 2026-05-18 — see spec docs/superpowers/specs/2026-05-18-local-overdrive-stack-design.md.
#
# Usage:
#   ./scripts/capture-fixture.sh                    # list recent prod runs, prompt
#   ./scripts/capture-fixture.sh overdrive_<TS>     # capture a specific run dir
#
# Requires:
#   - ai-vault unlocked with the ai-ils-reports key (run `ai-vault status` first)
#   - Run from the repo root
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${1:-}" ]]; then
    echo "Recent runs on ils-reports:"
    ai-vault exec ssh plchuser@ils-reports-ts \
        'ls -1td ~/chpl-overdrive-etl/out/overdrive_* | head -5'
    echo
    echo "Re-run with one of these names, e.g.:"
    echo "  $0 overdrive_20260518_070535"
    exit 0
fi

RUN_DIR="$1"

# Strip any path prefix the user might have included
RUN_DIR="${RUN_DIR##*/}"

if [[ ! "$RUN_DIR" =~ ^overdrive_[0-9]+_[0-9]+$ ]]; then
    echo "ERROR: $RUN_DIR does not look like a run-dir name (expected overdrive_<YYYYMMDD>_<HHMMSS>)" >&2
    exit 2
fi

if [[ -d "tests/fixtures/$RUN_DIR" ]]; then
    echo "ERROR: tests/fixtures/$RUN_DIR already exists. Delete or rename it first." >&2
    exit 3
fi

echo "Capturing $RUN_DIR from plchuser@ils-reports-ts..."
mkdir -p tests/fixtures
ai-vault exec scp -r "plchuser@ils-reports-ts:chpl-overdrive-etl/out/$RUN_DIR" tests/fixtures/

echo
echo "Captured (LOCAL-ONLY — tests/fixtures/ is gitignored):"
ls -la "tests/fixtures/$RUN_DIR" | head -10
echo
echo "Fixture contains patron-linked userIds — never commit. tests/fixtures/ is in .gitignore."
