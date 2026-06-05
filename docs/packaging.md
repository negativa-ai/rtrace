# Packaging RTrace

How the source tree is turned into prebuilt, relocatable bundles for
distribution. See [`../DISTRIBUTION.md`](../DISTRIBUTION.md) for the overall plan
and rationale. The build scripts live in [`../packaging/`](../packaging/).

## Outputs

Two self-contained tarballs, both Linux / x86-64:

| Tarball | Edition | Modes | Extra deps |
|---|---|---|---|
| `rtrace-light-linux-x64.tar.gz` | light | 1 | — |
| `rtrace-heavy-linux-x64.tar.gz` | heavy | 0 + 1 | angr, capstone, networkx |

Each unpacks to an `rtrace/` directory (the `RTRACE_HOME` bundle):

```
rtrace/
├── bin/rtrace            launcher (symlinked into ~/.local/bin by the installer)
├── python/               bundled relocatable interpreter + rtrace pkg + deps
├── dynamorio/            DynamoRIO runtime (bin64/drrun, lib64, ext, ...)
├── lib/librtrace.so      the DynamoRIO client (+ libcapstone for nucleus)
├── funseeker/FunSeeker   self-contained .NET publish
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
runs the scripts in an `ubuntu:20.04` container (glibc 2.31 → broad portability)
across an `edition: [light, heavy]` matrix, on `workflow_dispatch` and on `v*` tags,
and uploads the tarballs + `.sha256` as artifacts.

## Notes / knobs

- **No secrets required** — all submodules are public and cloned over https.
- **Pinned interpreter** — `PYTHON_BUILD_STANDALONE_URL` in the workflow pins a
  `python-build-standalone` release (currently CPython 3.11). When bumping it,
  confirm the URL resolves and that `angr==9.2.102` installs on that minor
  version (3.11 is the safe choice for the heavy edition's wheels).

## Validation status

Validated in the `rtrace-dev` container:

- FunSeeker `dotnet publish --self-contained -r linux-x64` against
  `src/FunSeeker/FunSeeker.fsproj` produces a standalone ELF executable.
- The light edition installs (`pip install .` + the `sr-utils` submodule) and its
  entry point, light-path imports (no angr/capstone/nucleus), and `--mode 0`
  rejection (exit 1) all work.

Not yet run end-to-end: the full `build-native.sh` (DynamoRIO compile) and
`build-bundle.sh` (relocatable Python + nucleus ABI build) on a clean checkout,
and a real mode-1 trace. These are the next things to exercise in CI.

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
