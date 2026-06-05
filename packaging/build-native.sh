#!/usr/bin/env bash
#
# build-native.sh -- build the shared native artifacts and lay them out under a
# bundle prefix ($RTRACE_HOME layout). This is the non-interactive, trimmed
# equivalent of the native-build steps in dev.sh, with the components that are
# never used at runtime removed (Ghidra, drltrace, libc-test, CUDA -- see
# DISTRIBUTION.md).
#
# Output layout (see paths.py):
#   <prefix>/dynamorio/        full DynamoRIO runtime (bin64, lib64, ext, ...)
#   <prefix>/lib/librtrace.so  the compiled DynamoRIO client
#   <prefix>/lib/libcapstone.* system capstone, needed by the nucleus module
#   <prefix>/funseeker/        self-contained .NET publish of FunSeeker
#   <prefix>/.nucleus-build/   nucleus python bindings, installed later into the
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

# --- 2. nucleus (native function-boundary detector + python bindings)
echo "==> [2/5] building nucleus"
( cd "$SUB/nucleus" && make clean && make setup && make )
# Keep the python-bindings source tree; build-bundle.sh installs it into the
# bundle interpreter (so it lands in the right site-packages).
rm -rf "$PREFIX/.nucleus-build"
cp -a "$SUB/nucleus/bindings/python" "$PREFIX/.nucleus-build"

# --- 3. DynamoRIO runtime
echo "==> [3/5] building DynamoRIO"
( cd "$SUB/dynamorio" && rm -rf build && mkdir build && cd build && cmake .. && make -j"$JOBS" )
# copy the built runtime into the bundle (bin64/drrun, lib64, ext, cmake, ...)
cp -a "$SUB/dynamorio/build/." "$PREFIX/dynamorio/"

# --- 4. librtrace.so (the DynamoRIO client) -- built against the runtime above
echo "==> [4/5] building librtrace.so"
export DYNAMORIO_HOME="$PREFIX/dynamorio"
( cd "$REPO_ROOT/src" && rm -rf build && mkdir build && cd build \
    && cmake -DDynamoRIO_DIR="$DYNAMORIO_HOME/cmake" .. && make -j"$JOBS" )
cp -aL "$REPO_ROOT/src/build/librtrace.so" "$PREFIX/lib/librtrace.so"

# --- 5. FunSeeker -- self-contained publish so no .NET runtime is needed on the host
# FunSeeker is an F# project (FunSeeker.fsproj).
echo "==> [5/5] publishing FunSeeker"
dotnet publish "$SUB/FunSeeker/src/FunSeeker/FunSeeker.fsproj" \
  -c Release --self-contained -r linux-x64 \
  -o "$PREFIX/funseeker"
chmod +x "$PREFIX/funseeker/FunSeeker" 2>/dev/null || true

echo "==> native build complete:"
( cd "$PREFIX" && find . -maxdepth 2 -type f \
    \( -name drrun -o -name 'librtrace.so' -o -name 'FunSeeker' \) -print )
