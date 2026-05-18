# Convenience targets for the OverDrive ETL repo.
#
# Sprint 1 (this file): `test`, `build`, `capture-fixture`.
# Sprint 2 adds: `publish` (build + push to ghcr.io).

.PHONY: test build capture-fixture help

help:
	@echo "Available targets:"
	@echo "  test              - Run pytest (via uv). Tests need fixtures captured first"
	@echo "                      via capture-fixture; otherwise tests skip cleanly."
	@echo "  build             - Build the OverDrive ETL container image locally."
	@echo "  capture-fixture   - Capture an OverDrive run dir from ils-reports as a"
	@echo "                      LOCAL-ONLY test fixture (never committed). Usage:"
	@echo "                      make capture-fixture RUN=overdrive_<YYYYMMDD>_<HHMMSS>"

test:
	uv run pytest

build:
	podman build -t localhost/chpl/overdrive-fetch:latest .

capture-fixture:
	./scripts/capture-fixture.sh $(RUN)
