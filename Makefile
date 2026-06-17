# RTrace build & install -- the `make` front-end to the packaging scripts.
#
# This drives the same two-step build the release workflow uses
# (.github/workflows/build-bundles.yml): build the shared native artifacts, then
# assemble a relocatable, self-contained $RTRACE_HOME bundle for one edition.
# The build logic itself lives in packaging/build-native.sh and
# packaging/build-bundle.sh; this Makefile only wires them together and adds an
# `install` target. See DISTRIBUTION.md / docs/packaging.md for the full design.
#
# Quick start:
#   make                      # build the light bundle into ./staging/rtrace
#   make install              # build + install to ~/.local/share/rtrace, symlink rtrace
#   make EDITION=heavy install # same, heavy edition (adds angr for rich mode)
#   make tarball              # build + produce rtrace-<edition>-linux-x64.tar.gz(+.sha256)
#   make clean                # remove build outputs
#
# Prerequisites: the build deps listed in docs/packaging.md (cmake,
# build-essential, g++-multilib, python3-dev, the zlib/unwind/snappy/lz4/xxhash
# and binutils -dev packages, dotnet-sdk-6.0) and initialized submodules
# (`make` initializes them on first use). Building capstone runs `sudo make
# install` so the system loader can find libcapstone for nucleus.

# --- knobs (override on the command line, e.g. `make EDITION=heavy`) ----------

# Edition: light (light mode only) or heavy (light + rich; adds angr).
EDITION ?= light

# Where the bundle is assembled (the tarball's top-level `rtrace/` dir).
PREFIX ?= $(CURDIR)/staging/rtrace

# Pinned relocatable interpreter (astral-sh/python-build-standalone, install_only
# = relocatable). This is the single source of truth for the bundled Python;
# verify/update the pin when bumping it (see docs/packaging.md).
PYTHON_URL ?= https://github.com/astral-sh/python-build-standalone/releases/download/20250106/cpython-3.11.11+20250106-x86_64-unknown-linux-gnu-install_only.tar.gz

# Install destination (relocatable, so this can be anywhere) and the dir the
# `rtrace` launcher is symlinked into.
INSTALL_PREFIX ?= $(HOME)/.local/share/rtrace
BINDIR ?= $(HOME)/.local/bin

# Tarball name, matching the release workflow / install.sh convention.
TARBALL := rtrace-$(EDITION)-linux-x64.tar.gz

.DEFAULT_GOAL := bundle
.PHONY: all bundle native tarball install uninstall submodules clean help

all: bundle

# Initialize submodules on first use (idempotent; only runs when missing).
submodules:
	@if [ ! -e submodules/dynamorio/CMakeLists.txt ]; then \
	  echo "==> initializing submodules"; \
	  git submodule update --init --recursive; \
	fi

# Build the shared native artifacts (DynamoRIO runtime, librtrace.so, capstone,
# nucleus sources, FunSeeker) into PREFIX.
native: submodules
	packaging/build-native.sh --prefix "$(PREFIX)"

# Assemble the relocatable bundle for EDITION on top of the native tree: bundled
# Python, the rtrace package + deps, nucleus bindings, and the launcher.
bundle: native
	packaging/build-bundle.sh \
	  --prefix "$(PREFIX)" \
	  --edition "$(EDITION)" \
	  --python-url "$(PYTHON_URL)"
	@echo "==> bundle ready: $(PREFIX) (edition=$(EDITION))"

# Package the bundle into a tarball + sha256 (what the release workflow uploads).
tarball: bundle
	tar -C "$(dir $(PREFIX))" -czf "$(TARBALL)" "$(notdir $(PREFIX))"
	sha256sum "$(TARBALL)" > "$(TARBALL).sha256"
	@echo "==> wrote $(TARBALL) (+ .sha256)"

# Install the freshly built bundle to INSTALL_PREFIX and symlink the launcher
# into BINDIR. The bundle is relocatable, so this is just a copy + symlink.
install: bundle
	rm -rf "$(INSTALL_PREFIX)"
	mkdir -p "$(dir $(INSTALL_PREFIX))"
	cp -a "$(PREFIX)" "$(INSTALL_PREFIX)"
	mkdir -p "$(BINDIR)"
	ln -sf "$(INSTALL_PREFIX)/bin/rtrace" "$(BINDIR)/rtrace"
	@echo "==> installed rtrace ($(EDITION)) to $(INSTALL_PREFIX)"
	@echo "    symlinked $(BINDIR)/rtrace -> $(INSTALL_PREFIX)/bin/rtrace"
	@case ":$$PATH:" in *":$(BINDIR):"*) ;; *) echo "    note: $(BINDIR) is not on PATH";; esac

uninstall:
	rm -rf "$(INSTALL_PREFIX)"
	rm -f "$(BINDIR)/rtrace"
	@echo "==> removed $(INSTALL_PREFIX) and $(BINDIR)/rtrace"

clean:
	rm -rf "$(CURDIR)/staging"
	rm -f rtrace-*-linux-x64.tar.gz rtrace-*-linux-x64.tar.gz.sha256
	rm -rf src/build submodules/dynamorio/build
	@echo "==> cleaned build outputs"

help:
	@echo "RTrace make targets:"
	@echo "  bundle (default)  build the EDITION bundle into PREFIX"
	@echo "  install           build + install to INSTALL_PREFIX, symlink into BINDIR"
	@echo "  tarball           build + package rtrace-<edition>-linux-x64.tar.gz(+.sha256)"
	@echo "  uninstall         remove an installed bundle + its launcher symlink"
	@echo "  clean             remove build outputs"
	@echo ""
	@echo "Variables: EDITION=$(EDITION)  PREFIX=$(PREFIX)"
	@echo "           INSTALL_PREFIX=$(INSTALL_PREFIX)  BINDIR=$(BINDIR)"
