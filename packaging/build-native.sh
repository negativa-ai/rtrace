#!/usr/bin/env bash
#
# build-native.sh -- build the shared native artifacts and lay them out under a
# bundle prefix ($RTRACE_HOME layout). This is the non-interactive, trimmed
# equivalent of the native-build steps in dev.sh, with the components that are
# never used at runtime removed (Ghidra, drltrace, libc-test, CUDA -- see
# DISTRIBUTION.md).
#
# Output layout (see paths.py):
#   <prefix>/dynamorio/        minimal DynamoRIO runtime (drrun + the shared libs
#                              librtrace.so needs, in the layout drrun expects)
#   <prefix>/lib/librtrace.so  the compiled DynamoRIO client
#   <prefix>/lib/libcapstone.* system capstone, needed by the nucleus module
#   <prefix>/funseeker/        self-contained .NET publish of FunSeeker
#   <prefix>/.nucleus-src/     nucleus sources, compiled later against the
#                              bundle interpreter by build-bundle.sh
#
# Usage: packaging/build-native.sh --prefix <dir>
#
# Prerequisites (see packaging/README.md / the CI workflow for the exact apt set):
#   cmake, build-essential, g++-multilib, python3-dev,
#   zlib1g-dev libunwind-dev libsnappy-dev liblz4-dev libxxhash-dev,
#   dotnet-sdk-6.0, and initialized submodules.
set -euo pipefail

PREFIX=""
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$PREFIX" ] || { echo "error: --prefix is required" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUB="$REPO_ROOT/submodules"
PREFIX="$(mkdir -p "$PREFIX" && cd "$PREFIX" && pwd)"
JOBS="$(nproc 2>/dev/null || echo 4)"

echo "==> repo:   $REPO_ROOT"
echo "==> prefix: $PREFIX"
mkdir -p "$PREFIX/lib" "$PREFIX/dynamorio" "$PREFIX/funseeker"

# --- 1. system capstone (libcapstone) -- required by the nucleus native module
echo "==> [1/5] building capstone"
( cd "$SUB/capstone" && ./make.sh )
# install the shared lib into the bundle (and the system, so nucleus links it)
( cd "$SUB/capstone" && sudo ./make.sh install )
# stage the runtime shared object for the bundle
cp -aL "$SUB/capstone"/libcapstone.so* "$PREFIX/lib/" 2>/dev/null || \
  cp -aL /usr/lib*/libcapstone.so* "$PREFIX/lib/" 2>/dev/null || true

# --- 2. nucleus python-bindings source (compiled later against the bundle
# interpreter by build-bundle.sh). The bindings' setup.py globs ../../*.cc for the
# core sources, so stage the WHOLE nucleus tree, not just bindings/python. The core
# `make` target builds an unused standalone binary and is skipped; the binutils
# deps that its `make setup` installs are provided by the build image instead.
echo "==> [2/5] staging nucleus sources"
rm -rf "$PREFIX/.nucleus-src"
cp -a "$SUB/nucleus" "$PREFIX/.nucleus-src"
rm -rf "$PREFIX/.nucleus-src/.git" "$PREFIX/.nucleus-src/obj"

# --- 3. DynamoRIO runtime
echo "==> [3/5] building DynamoRIO"
DRB="$SUB/dynamorio/build"
( cd "$SUB/dynamorio" && rm -rf build && mkdir build && cd build && cmake .. && make -j"$JOBS" )

# --- 4. librtrace.so (the DynamoRIO client) -- built against the build tree above
echo "==> [4/5] building librtrace.so"
( cd "$REPO_ROOT/src" && rm -rf build && mkdir build && cd build \
    && cmake -DDynamoRIO_DIR="$DRB/cmake" .. && make -j"$JOBS" )
cp -aL "$REPO_ROOT/src/build/librtrace.so" "$PREFIX/lib/librtrace.so"

# Stage only the DynamoRIO files used at runtime (~5 MB instead of the >1 GB
# build tree). drrun derives DYNAMORIO_HOME from its own path and DynamoRIO's
# private loader resolves the client's libraries from <home>/lib64/release and
# <home>/ext/lib64/release, so this directory layout must be preserved.
# librtrace.so links drmgr/drreg/drx/drwrap as shared extensions (drcontainers
# is static); .debug files and static archives are not needed.
rm -rf "$PREFIX/dynamorio"
mkdir -p "$PREFIX/dynamorio/bin64" "$PREFIX/dynamorio/lib64/release" \
         "$PREFIX/dynamorio/ext/lib64/release"
cp -a "$DRB/bin64/drrun" "$PREFIX/dynamorio/bin64/"
cp -a "$DRB/lib64/release/libdynamorio.so" "$DRB/lib64/release/libdrpreload.so" \
      "$PREFIX/dynamorio/lib64/release/"
for ext_lib in drmgr drreg drx drwrap; do
  cp -a "$DRB/ext/lib64/release/lib$ext_lib.so" "$PREFIX/dynamorio/ext/lib64/release/"
done

# --- 5. FunSeeker -- self-contained publish so no .NET runtime is needed on the host
# FunSeeker is an F# project (FunSeeker.fsproj). InvariantGlobalization drops the
# libicu runtime requirement (not present on minimal hosts); FunSeeker analyzes
# binaries and never needs culture data.
echo "==> [5/5] publishing FunSeeker"
dotnet publish "$SUB/FunSeeker/src/FunSeeker/FunSeeker.fsproj" \
  -c Release --self-contained -r linux-x64 \
  -p:DebugType=None -p:DebugSymbols=false -p:InvariantGlobalization=true \
  -o "$PREFIX/funseeker"
chmod +x "$PREFIX/funseeker/FunSeeker" 2>/dev/null || true

echo "==> native build complete:"
( cd "$PREFIX" && find . -maxdepth 2 -type f \
    \( -name drrun -o -name 'librtrace.so' -o -name 'FunSeeker' \) -print )
