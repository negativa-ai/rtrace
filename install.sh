#!/bin/sh
#
# RTrace installer: downloads a prebuilt bundle from GitHub Releases, verifies
# its sha256 checksum, extracts it, and links the `rtrace` launcher onto PATH.
#
#   curl -fsSL https://raw.githubusercontent.com/negativa-ai/rtrace/main/install.sh | sh
#   curl -fsSL ... | sh -s -- --edition heavy
#   curl -fsSL ... | sh -s -- --version v0.1.0-alpha
#   curl -fsSL ... | sh -s -- --uninstall
#
# Options:
#   --edition light|heavy   light = --mode 1 only (default); heavy adds --mode 0
#   --version vX.Y.Z        install a specific release (default: latest)
#   --prefix DIR            install root (default: ~/.local/share)
#   --bin-dir DIR           where the rtrace symlink goes (default: ~/.local/bin)
#   --uninstall             remove an existing install
#
# Requires: curl, tar, sha256sum, and glibc >= 2.35 (Ubuntu 22.04+, Debian 12+,
# Fedora 36+, RHEL 9+). On older distros, build from source instead -- see
# https://github.com/negativa-ai/rtrace#install-from-source
set -eu

REPO="negativa-ai/rtrace"
EDITION="light"
VERSION="latest"
PREFIX="${HOME}/.local/share"
BIN_DIR="${HOME}/.local/bin"
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --edition)   EDITION="$2"; shift 2;;
    --version)   VERSION="$2"; shift 2;;
    --prefix)    PREFIX="$2"; shift 2;;
    --bin-dir)   BIN_DIR="$2"; shift 2;;
    --uninstall) UNINSTALL=1; shift;;
    -h|--help)   sed -n '2,20p' "$0" 2>/dev/null || true; exit 0;;
    *) echo "install.sh: unknown option: $1" >&2; exit 2;;
  esac
done

HOME_DIR="$PREFIX/rtrace"
LINK="$BIN_DIR/rtrace"

if [ "$UNINSTALL" = 1 ]; then
  echo "Removing $HOME_DIR and $LINK"
  rm -rf "$HOME_DIR"
  rm -f "$LINK"
  echo "rtrace uninstalled."
  exit 0
fi

case "$EDITION" in light|heavy) ;; *)
  echo "install.sh: --edition must be 'light' or 'heavy' (got '$EDITION')" >&2; exit 2;;
esac

for tool in curl tar sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "install.sh: required tool not found: $tool" >&2; exit 1; }
done

# Soft glibc check: old distros fail later with cryptic GLIBC_X.YY errors.
glibc="$(ldd --version 2>/dev/null | sed -n '1s/.* \([0-9][0-9]*\.[0-9][0-9]*\)$/\1/p')"
if [ -n "$glibc" ]; then
  major="${glibc%%.*}"; minor="${glibc#*.}"
  if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 35 ]; }; then
    echo "WARNING: glibc $glibc detected; the prebuilt bundles need >= 2.35." >&2
    echo "         The install will proceed but rtrace will likely not run;" >&2
    echo "         see the README for building from source." >&2
  fi
fi

ASSET="rtrace-${EDITION}-linux-x64.tar.gz"
if [ "$VERSION" = "latest" ]; then
  BASE_URL="https://github.com/$REPO/releases/latest/download"
else
  BASE_URL="https://github.com/$REPO/releases/download/$VERSION"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $ASSET ($VERSION)..."
curl -fL --progress-bar -o "$TMP/$ASSET" "$BASE_URL/$ASSET"
curl -fsSL -o "$TMP/$ASSET.sha256" "$BASE_URL/$ASSET.sha256"

echo "Verifying checksum..."
( cd "$TMP" && sha256sum -c "$ASSET.sha256" )

echo "Installing to $HOME_DIR..."
rm -rf "$HOME_DIR"
mkdir -p "$PREFIX" "$BIN_DIR"
tar -C "$TMP" -xzf "$TMP/$ASSET"
mv "$TMP/rtrace" "$HOME_DIR"
ln -sf "$HOME_DIR/bin/rtrace" "$LINK"

echo "Installed rtrace ($(cat "$HOME_DIR/EDITION") edition) -> $LINK"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "NOTE: $BIN_DIR is not on your PATH. Add it, e.g.:"
     echo "      export PATH=\"$BIN_DIR:\$PATH\"";;
esac
echo "Try: rtrace --logdir /tmp/trace --mode 1 -- /bin/ls"
