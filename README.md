# RTrace

A high accuracy library function call tracer.

RTrace runs your program under [DynamoRIO](https://dynamorio.org/) and records
which library functions it actually executes, even in stripped binaries —
function boundaries are recovered with FunSeeker (CET binaries), Nucleus
(non-CET), or symbol tables when present.

## Install (prebuilt bundles)

```sh
curl -fsSL https://raw.githubusercontent.com/negativa-ai/rtrace/main/install.sh | sh
```

Two self-contained editions for Linux x86-64 — no Python, .NET, or compiler
needed on your machine:

| Edition | Modes | Tarball |
|---|---|---|
| **light** | `--mode light` | `rtrace-light-linux-x64.tar.gz` (~120 MB) |
| **heavy** | `--mode light` and `--mode rich` | `rtrace-heavy-linux-x64.tar.gz` (~250 MB) |

The installer takes `--edition light|heavy` (default `light`), `--version vX.Y.Z`
(default latest), `--prefix` / `--bin-dir` to relocate, and `--uninstall`:

```sh
curl -fsSL https://raw.githubusercontent.com/negativa-ai/rtrace/main/install.sh | sh -s -- --edition heavy
```

It downloads the release tarball, verifies its sha256 checksum, extracts to
`~/.local/share/rtrace`, and links `~/.local/bin/rtrace` (make sure that's on
your `PATH`).

<details>
<summary>Manual install (no script)</summary>

```sh
EDITION=light  # or: heavy
curl -fsSLO https://github.com/negativa-ai/rtrace/releases/latest/download/rtrace-$EDITION-linux-x64.tar.gz
curl -fsSLO https://github.com/negativa-ai/rtrace/releases/latest/download/rtrace-$EDITION-linux-x64.tar.gz.sha256
sha256sum -c rtrace-$EDITION-linux-x64.tar.gz.sha256

mkdir -p ~/.local/share ~/.local/bin
tar -C ~/.local/share -xzf rtrace-$EDITION-linux-x64.tar.gz
ln -sf ~/.local/share/rtrace/bin/rtrace ~/.local/bin/rtrace
```

To uninstall, delete `~/.local/share/rtrace` and the `~/.local/bin/rtrace`
symlink.
</details>

### Compatibility

The bundles are built on Ubuntu 22.04 and run on any Linux x86-64 distribution
with **glibc >= 2.35**: Ubuntu 22.04+, Debian 12+, Fedora 36+, RHEL 9+, and
their derivatives. On older distributions (e.g. Ubuntu 20.04) the native
components fail with `GLIBC_X.YY not found` errors — there,
[install from source](#install-from-source) instead.

## Usage

```sh
rtrace --logdir ./trace-out --mode light -- your_program --its --args
```

- `--mode light`: records which library functions were executed.
- `--mode rich` (heavy edition only): additionally reconstructs the
  call graph and analyzes function prototypes.

Detected function calls are written to `function-executed-<pid>-<tid>.json`
under the log directory.

## Install from source

Needs Ubuntu 22.04 or newer (or adjust the package names to your distro),
roughly 15 minutes of compile time, and ~2 GB of disk.

```sh
# toolchain + build dependencies
sudo apt-get install -y git curl ca-certificates cmake build-essential \
    g++-multilib python3 python3-dev zlib1g-dev libunwind-dev libsnappy-dev \
    liblz4-dev libxxhash-dev binutils-dev binutils-multiarch-dev dotnet-sdk-6.0

git clone --recurse-submodules https://github.com/negativa-ai/rtrace.git
cd rtrace

# build the native artifacts (DynamoRIO, the tracer client, FunSeeker, ...)
packaging/build-native.sh --prefix /tmp/staging/rtrace

# assemble a relocatable bundle around them (downloads a standalone Python)
packaging/build-bundle.sh --prefix /tmp/staging/rtrace --edition light \
    --python-url "https://github.com/astral-sh/python-build-standalone/releases/download/20250106/cpython-3.11.11+20250106-x86_64-unknown-linux-gnu-install_only.tar.gz"

# install
mkdir -p ~/.local/share ~/.local/bin
cp -a /tmp/staging/rtrace ~/.local/share/rtrace
ln -sf ~/.local/share/rtrace/bin/rtrace ~/.local/bin/rtrace
```

Pass `--edition heavy` to `build-bundle.sh` for the heavy edition. See
[docs/packaging.md](docs/packaging.md) for how the bundles are put together.

## Development

1. Start the dev container: `./dev.sh`
2. Trace a workload:
```bash
LOG_DIR=/path/to/tracing/results
CMD=the_workload_cmd
MODE=light # rich for full prototype analysis, light for lightweight tracing
python /home/ubuntu/repos/rtrace/src/rtrace/main.py --logdir $LOG_DIR --mode $MODE -- $CMD
```
3. All detected function calls are recorded in files named `function-executed-xxx-xxxx.json` under `LOG_DIR`.
