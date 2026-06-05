# Packaging RTrace

How the source tree is turned into prebuilt, relocatable bundles for
distribution. See [`../DISTRIBUTION.md`](../DISTRIBUTION.md) for the overall plan
and rationale. The build scripts live in [`../packaging/`](../packaging/).

## Outputs

Two self-contained tarballs, both Linux / x86-64:

| Tarball | Edition | Modes | Extra deps | ~Size |
|---|---|---|---|---|
| `rtrace-light-linux-x64.tar.gz` | light | 1 | — | 120 MB |
| `rtrace-heavy-linux-x64.tar.gz` | heavy | 0 + 1 | angr, capstone, networkx | 250 MB |

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
  (`.` vs `.[heavy]`), installs `sr-utils` and the `nucleus` bindings, and writes
  the launcher.

We bundle our own Python (astral-sh/python-build-standalone) rather than reuse
the user's, because `nucleus` is a native CPython-ABI module — bundling fixes the
ABI and keeps the end-user install build-free. See the `build-bundle.sh` header.

## CI

[`../.github/workflows/build-bundles.yml`](../.github/workflows/build-bundles.yml)
runs the scripts in an `ubuntu:24.04` container (glibc 2.39, matching
`_docker/Dockerfile`) across an `edition: [light, heavy]` matrix, on
`workflow_dispatch` and on `v*` tags, and uploads the tarballs + `.sha256` as
artifacts.

A `smoke-test` job then installs each tarball on a **clean** `ubuntu:24.04`
container (no build tools, no libicu, no binutils) and proves it is genuinely
self-contained: a real `--mode 1` trace of `/bin/ls` (exercising drrun,
librtrace.so, postprocessing, and FunSeeker boundary detection on the stripped
CET system libraries), a nucleus boundary-detection call, heavy-edition imports
(`angr`/`capstone`/`networkx`), and the light edition's `--mode 0` refusal.
A full mode-0 run is deliberately excluded: it runs angr prototype analysis
over every loaded module (libc included), far too slow for CI.

## Notes / knobs

- **No secrets required** — all submodules are public and cloned over https.
- **Pinned interpreter** — `PYTHON_BUILD_STANDALONE_URL` in the workflow pins a
  `python-build-standalone` release (currently CPython 3.11). When bumping it,
  confirm the URL resolves and that `angr==9.2.102` installs on that minor
  version (3.11 is the safe choice for the heavy edition's wheels).

## Validation status

- The full build pipeline (both editions) passed in real CI.
- Both bundles were exercised on a pristine `ubuntu:24.04` container (no build
  tools): mode-1 trace of `/bin/ls` end-to-end (FunSeeker boundary detection on
  all 5 stripped CET modules, 3992 executed functions attributed), nucleus
  detecting 271 entries in `/bin/ls`, heavy `import angr`, and light `--mode 0`
  refusal. The same checks now run in CI as the `smoke-test` job.
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

## Next (Phase 3/4)

Signing (`SHA256SUMS` + minisign/GPG), the `curl | sh` installer with
`--edition`, and the tag-driven GitHub Release publish.
