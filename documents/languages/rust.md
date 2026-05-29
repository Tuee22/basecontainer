---
name: languages-rust
description: Rust conventions inside the basecontainer base image.
type: guide
---

# Rust

The base image installs the latest stable Rust toolchain via `rustup`:

```
RUSTUP_TOOLCHAIN=stable
```

with `llvm-tools-preview` and `rustfmt` components. Caches:

* `CARGO_HOME=/opt/cache/cargo`
* `CARGO_TARGET_DIR=/opt/build/rust/target`
* `CARGO_HTTP_TIMEOUT=120`
* `CARGO_NET_RETRY=5`

LLVM LLD and BOLT (from the apt LLVM family, see [cpp.md](cpp.md)) are
available for optimised Rust builds when projects opt in.
