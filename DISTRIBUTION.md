# RTrace Distribution Plan

This document captures how RTrace is packaged and distributed to end users. The
goal is an **easy, native (no-build-from-source) install** that is versioned and
signed — not a developer build.

## Summary of decisions

- **No build from source for end users.** Ship prebuilt, relocatable artifacts.
- **Native install, no Docker.** Self-contained tarball on GitHub Releases,
  fetched and verified by a `curl | sh` installer (the same pattern as `uv`,
  `rustup`, `deno`).
- **Two editions** (see below): `light` (mode 1 only) and `heavy` (modes 0 + 1).
- **Linux / x86-64 only** for v1 (matches the current dev environment). Built on
  an old-glibc base (manylinux_2_28 / Ubuntu 20.04) for broad portability.

## Why not the alternatives

- **apt PPA (Launchpad):** Launchpad builders are network-isolated and build from
  source using only archive dependencies. RTrace needs NuGet restore (FunSeeker),
  private submodules, and a DynamoRIO build — all of which violate that model.
- **Self-hosted apt repo:** viable, but the audience needs a native install rather
  than apt specifically, so a signed tarball + installer is simpler and distro-agnostic.
- **Docker image:** rejected — users need to run RTrace directly on the host.

## Component necessity (what we bundle vs. drop)

Traced from the runtime path (`main.py` → `drrun -c librtrace.so` → `postprocess`).

**Bundled (required):**
- DynamoRIO runtime + `librtrace.so` + extensions (drmgr/drreg/drx/drwrap/drcontainers)
- Python: pyelftools, pandas, srutils (sr-utils)
- Boundary-detection backends: `nucleus` (native) + `FunSeeker` (.NET, self-contained publish)

**Dropped (never invoked at runtime):**
- **Ghidra / a JRE / pyghidra** — zero references; only commented-out code. Removing
  this eliminates the entire JVM payload.
- **drltrace** — built by `dev.sh` but never referenced by RTrace.
- **pygraphviz / graphviz** — `write_dot` lives only in `create_cfg_partial`, whose
  only caller is commented out.
- **numpy** — imported but never used (`np.` appears nowhere).
- **requests** — listed in requirements but unused.
- **libc-test, debloater-eval** submodules — test/benchmark fixtures.

## Editions

The native tracer (`librtrace.so` + DynamoRIO) takes `--mode` as a **runtime flag**,
so a **single native bundle** serves both editions. The editions differ **only** in
Python dependencies.

| | `rtrace-light` | `rtrace-heavy` |
|---|---|---|
| Modes | 1 only | 0 + 1 |
| Native tracer (DynamoRIO + `librtrace.so`) | yes | yes |
| Boundary detection: linear + nucleus + FunSeeker(.NET) | yes | yes |
| Python base: pyelftools, pandas, srutils | yes | yes |
| **angr + capstone + networkx** (mode-0 prototype/CFG analysis) | no | yes |
| `--mode 0` | error → "install rtrace-heavy" | works |

The only weight difference is **angr** (with z3/unicorn/pyvex/claripy); capstone and
networkx are small tag-alongs that are also only needed in mode 0.

Mode gating evidence:
- `angr`: `_set_function_prototype`, gated by `analyze_function_prototypes=(mode==0)`.
- `capstone`: `Library.decode()`, only called `if mode==0`.
- `networkx`: `create_cfg`, only in the `if mode==0` block of `postprocess`.

## Phased plan

### Phase 1 — Refactor + packaging (foundation) — IN PROGRESS
1. `pyproject.toml` with the `rtrace` package + `rtrace` console-script entry point.
2. **Lazy-import** the heavy deps so the light install does not require them:
   `angr`, `capstone`, `networkx`/`write_dot` (and `nucleus`, which ships in both).
3. Dependency extras: base = light; `[heavy]` extra = `angr, capstone, networkx`.
4. `--mode 0` guard in the light edition with a clear "install rtrace-heavy" message.
5. `RTRACE_HOME`-relative path resolution (removes the hardcoded `/home/ubuntu/...`
   paths and the conda shebangs).
- **Checkpoint:** light traces mode 1 and heavy traces mode 0, locally.

### Phase 2 — CI artifact build (one shared native tree)
Build `librtrace.so` + DynamoRIO runtime, nucleus (+ bundled libcapstone), and
FunSeeker via `dotnet publish --self-contained -r linux-x64`. Resolve the private
submodules via deploy keys. Build on an old-glibc base for portability. No Ghidra,
no JRE, no drltrace.

### Phase 3 — Two relocatable tarballs
- `rtrace-light-vX-linux-x64.tar.gz` = native tree + nucleus + FunSeeker + light venv.
- `rtrace-heavy-vX-linux-x64.tar.gz` = the same + angr venv.
- Each with `SHA256SUMS` + a minisign/GPG signature.

### Phase 4 — Installer + GitHub Releases
`curl … | sh` installer with `--edition light|heavy` (default light): verifies the
signature, extracts to `~/.local/share/rtrace`, and symlinks `rtrace` into
`~/.local/bin`. Tag-driven release workflow. Documented in `README.md`.

## Install layout (bundle)

```
$RTRACE_HOME/                 # e.g. ~/.local/share/rtrace
├── dynamorio/bin64/drrun     # DynamoRIO runtime
├── lib/librtrace.so          # the tracer client
├── funseeker/FunSeeker       # self-contained .NET publish (both editions)
├── nucleus/                  # native module + libcapstone (both editions)
└── venv/                     # relocatable Python interpreter + deps
```

The `rtrace` launcher sets `RTRACE_HOME` and execs the bundled venv Python.
