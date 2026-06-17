#!/usr/bin/env bash
#
# build-bundle.sh -- turn a native staging tree (from build-native.sh) into a
# complete, relocatable RTRACE_HOME bundle for one edition by adding a
# relocatable Python interpreter, the rtrace package + its dependencies, the
# nucleus bindings, and the `rtrace` launcher.
#
# We bundle our OWN relocatable Python (astral-sh/python-build-standalone, the
# same interpreter uv ships) rather than reusing the user's: nucleus is a native
# CPython-ABI module, so a prebuilt nucleus.so must match one exact interpreter.
# Bundling fixes that ABI and keeps the install build-free (extract + symlink).
#
# Editions (see DISTRIBUTION.md):
#   light -- installs `rtrace`           (mode 1 only)
#   heavy -- installs `rtrace[heavy]`    (modes 0 + 1; adds angr)
#
# Usage:
#   packaging/build-bundle.sh --prefix <dir> --edition light|heavy \
#       --python-url <python-build-standalone tarball url>
#   packaging/build-bundle.sh --prefix <dir> --edition heavy \
#       --python-home <dir-with-relocatable-python>
set -euo pipefail

PREFIX="" EDITION="" PYTHON_URL="" PYTHON_HOME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix)      PREFIX="$2"; shift 2;;
    --edition)     EDITION="$2"; shift 2;;
    --python-url)  PYTHON_URL="$2"; shift 2;;
    --python-home) PYTHON_HOME="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$PREFIX" ]  || { echo "error: --prefix is required" >&2; exit 2; }
case "$EDITION" in light|heavy) ;; *) echo "error: --edition must be light|heavy" >&2; exit 2;; esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="$(cd "$PREFIX" && pwd)"
PY_PREFIX="$PREFIX/python"
PY="$PY_PREFIX/bin/python3"

echo "==> bundling edition=$EDITION into $PREFIX"

# --- 1. relocatable Python interpreter ---------------------------------------
rm -rf "$PY_PREFIX"
mkdir -p "$PY_PREFIX"
if [ -n "$PYTHON_URL" ]; then
  echo "==> fetching relocatable python: $PYTHON_URL"
  tmp="$(mktemp -d)"
  curl -fsSL "$PYTHON_URL" -o "$tmp/python.tar.gz"
  # python-build-standalone tarballs extract to a top-level `python/` directory.
  tar -xzf "$tmp/python.tar.gz" -C "$tmp"
  cp -a "$tmp/python/." "$PY_PREFIX/"
  rm -rf "$tmp"
elif [ -n "$PYTHON_HOME" ]; then
  cp -a "$PYTHON_HOME/." "$PY_PREFIX/"
else
  echo "error: provide --python-url or --python-home" >&2; exit 2
fi
"$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PY" -m pip install --no-warn-script-location -q --upgrade pip

# --- 2. the rtrace package (selects the edition's dependency set) -------------
TARGET="."
[ "$EDITION" = "heavy" ] && TARGET=".[heavy]"
echo "==> pip install rtrace ($TARGET)"
"$PY" -m pip install --no-warn-script-location "$REPO_ROOT/$TARGET"

# --- 3. nucleus bindings (native) -- both editions ----------------------------
# Sources staged by build-native.sh into <prefix>/.nucleus-src; compile into the
# bundle interpreter so it lands in the bundle's site-packages with a matching ABI.
if [ -d "$PREFIX/.nucleus-src" ]; then
  echo "==> install nucleus bindings into bundle interpreter (force g++)"
  NUC="$PREFIX/.nucleus-src/bindings/python"
  # python-build-standalone is a clang-built interpreter, so its sysconfig drives
  # distutils to clang++ (which is not installed in the build image). Force the
  # system g++/gcc -- the compiler the dev container validated nucleus against --
  # so pybind11's cpp_flag probe and the extension build succeed.
  export CC="${CC:-gcc}" CXX="${CXX:-g++}"
  # Link libstdc++/libgcc statically: the module otherwise binds GLIBCXX_*
  # symbols of the build image's libstdc++, breaking hosts with an older one.
  # distutils appends $LDFLAGS to its shared-object link line.
  export LDFLAGS="-static-libstdc++ -static-libgcc${LDFLAGS:+ $LDFLAGS}"
  # nucleus's setup.py imports pybind11 at build time. dev.sh built it against the
  # conda interpreter that already had pybind11; here we install it into the bundle
  # interpreter and build without isolation so the build sees it.
  "$PY" -m pip install --no-warn-script-location pybind11==2.13.6
  "$PY" -m pip install --no-warn-script-location --no-build-isolation "$NUC" \
    || ( cd "$NUC" && "$PY" setup.py install )
  rm -rf "$PREFIX/.nucleus-src"
  # nucleus links libbfd from binutils-multiarch (which pulls in libsframe etc.);
  # those exist on the build image but not on minimal hosts. Ship them next to
  # libcapstone in <prefix>/lib, which the launcher puts on LD_LIBRARY_PATH.
  NUC_SO="$(ls "$PY_PREFIX"/lib/python*/site-packages/nucleus*.so)"
  ldd "$NUC_SO" | awk '/=> \//{print $3}' \
    | grep -E 'libbfd|libopcodes|libsframe|libz\.so|libzstd' \
    | while read -r dep; do cp -aL "$dep" "$PREFIX/lib/"; done
fi

# --- 4. launcher --------------------------------------------------------------
mkdir -p "$PREFIX/bin"
cat > "$PREFIX/bin/rtrace" <<'LAUNCHER'
#!/usr/bin/env bash
# rtrace launcher: resolves RTRACE_HOME from its own location (works through the
# ~/.local/bin symlink created by the installer) and runs the bundled interpreter.
set -euo pipefail
self="$(readlink -f "$0")"
RTRACE_HOME="$(cd "$(dirname "$self")/.." && pwd)"
export RTRACE_HOME
export LD_LIBRARY_PATH="$RTRACE_HOME/lib:$RTRACE_HOME/dynamorio/lib64:${LD_LIBRARY_PATH:-}"
exec "$RTRACE_HOME/python/bin/python3" -m rtrace.main "$@"
LAUNCHER
chmod +x "$PREFIX/bin/rtrace"

# record edition for diagnostics / the installer
echo "$EDITION" > "$PREFIX/EDITION"

echo "==> bundle complete: $PREFIX (edition=$EDITION)"
echo "    launcher: $PREFIX/bin/rtrace"
