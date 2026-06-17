# Packaging RTrace

How the source tree is turned into prebuilt, relocatable bundles for
distribution. See [`../DISTRIBUTION.md`](../DISTRIBUTION.md) for the overall plan
and rationale. The build scripts live in [`../packaging/`](../packaging/).

## Outputs

Two self-contained tarballs, both Linux / x86-64:

| Tarball | Edition | Modes | Extra deps | ~Size |
|---|---|---|---|---|
| `rtrace-light-linux-x64.tar.gz` | light | light | — | 120 MB |
| `rtrace-heavy-linux-x64.tar.gz` | heavy | light + rich | angr, capstone | 250 MB |

Each unpacks to an `rtrace/` directory (the `RTRACE_HOME` bundle):

```
rtrace/
├── bin/rtrace            launcher (symlinked into ~/.local/bin by the installer)
├── python/               bundled relocatable interpreter + rtrace pkg + deps
├── dynamorio/            minimal DynamoRIO runtime (drrun + libdynamorio +
│                         the drmgr/drreg/drx/drwrap extensions, ~5 MB)
├── lib/librtrace.so      the DynamoRIO client, plus the native libs nucleus
│                         needs (libcapstone, libbfd-multiarch, libsframe, ...)
├── funseeker/FunSeeker   self-contained .NET publish (invariant globalization,
│                         so no libicu needed on the host)
└── EDITION               "light" | "heavy"
```

## Scripts

- **`packaging/build-native.sh --prefix <dir>`** — builds the shared native
  artifacts (DynamoRIO, `librtrace.so`, capstone, nucleus, FunSeeker) into the
  bundle layout. The native tree is identical for both editions.
- **`packaging/build-bundle.sh --prefix <dir> --edition light|heavy --python-url <url>`** —
  adds the bundled Python, installs the `rtrace` package for the chosen edition
  (`.` vs `.[heavy]`), installs the `nucleus` bindings, and writes
  the launcher.

We bundle our own Python (astral-sh/python-build-standalone) rather than reuse
the user's, because `nucleus` is a native CPython-ABI module — bundling fixes the
ABI and keeps the end-user install build-free. See the `build-bundle.sh` header.

## CI

[`../.github/workflows/build-bundles.yml`](../.github/workflows/build-bundles.yml)
runs the scripts in an `ubuntu:22.04` container across an
`edition: [light, heavy]` matrix, on `workflow_dispatch` and on `v*` tags, and
uploads the tarballs + `.sha256` as artifacts.

The build base is deliberately *older* than the 24.04 dev environment: compiled
binaries bind to the build base's glibc symbol versions, so the build base sets
the oldest distro users can run on. Building on 22.04 gives a **glibc >= 2.35**
floor (Ubuntu 22.04+, Debian 12+, Fedora 36+, RHEL 9+). The nucleus module is
additionally linked with `-static-libstdc++` so it does not depend on the
host's libstdc++ version. The bundled Python (python-build-standalone) and
FunSeeker (self-contained .NET) are portable well below this floor; only the
components we compile set it.

A `smoke-test` job then installs each tarball on a **clean** `ubuntu:22.04`
container — the oldest supported distro, so it also guards the glibc floor —
(no build tools, no libicu, no binutils) and proves it is genuinely
self-contained: a real `--mode light` trace of `/bin/ls` (exercising drrun,
librtrace.so, postprocessing, and FunSeeker boundary detection on the stripped
CET system libraries), a nucleus boundary-detection call, heavy-edition imports
(`angr`/`capstone`), and the light edition's `--mode rich` refusal.
A full rich-mode run is deliberately excluded: it runs angr prototype analysis
over every loaded module (libc included), far too slow for CI.

## Releases

On `v*` tags, after the smoke tests pass, the `release` job publishes a GitHub
Release with both tarballs and their `.sha256` checksums attached, and notes
containing verify + install instructions. It needs no secrets beyond the
workflow's built-in `GITHUB_TOKEN` (`contents: write`).

Cutting a release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Notes / knobs

- **No secrets required** — all submodules are public and cloned over https.
- **Pinned interpreter** — `PYTHON_BUILD_STANDALONE_URL` in the workflow pins a
  `python-build-standalone` release (currently CPython 3.11). When bumping it,
  confirm the URL resolves and that `angr==9.2.102` installs on that minor
  version (3.11 is the safe choice for the heavy edition's wheels).

## Validation status

- The full build pipeline (both editions) passed in real CI, and the published
  v0.1.0-alpha assets were installed and exercised end-to-end as an
  unprivileged user on pristine containers (both editions).
- A 22.04-built light bundle was tested across a distro matrix; every component
  (bundled python, nucleus, FunSeeker, full mode-1 trace) passes on
  ubuntu 22.04 / 24.04, debian 12 / 13, and fedora 42. Ubuntu 20.04
  (glibc 2.31, past standard EOL) fails in drrun/nucleus as expected — that is
  the floor.
- FunSeeker output was verified byte-identical with and without
  `InvariantGlobalization=true` + `DebugType=None` on `/bin/ls` and libc.

## Local build (if you have the submodules + toolchain)

```bash
git submodule update --init --recursive
packaging/build-native.sh --prefix /tmp/staging/rtrace
packaging/build-bundle.sh  --prefix /tmp/staging/rtrace --edition light \
    --python-url "<python-build-standalone install_only tarball url>"
tar -C /tmp/staging -czf rtrace-light-linux-x64.tar.gz rtrace
```

## Installer

[`../install.sh`](../install.sh) is the end-user `curl | sh` installer: it
downloads the requested edition from GitHub Releases (latest by default, or
`--version vX.Y.Z`), verifies the sha256 checksum, extracts to
`~/.local/share/rtrace`, links `~/.local/bin/rtrace`, warns when the host's
glibc is below the 2.35 floor or `~/.local/bin` is not on `PATH`, and supports
`--uninstall`. It is plain POSIX sh and needs only curl, tar, and sha256sum.
