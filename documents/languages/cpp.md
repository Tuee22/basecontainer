---
name: languages-cpp
description: C/C++/LLVM conventions inside the basecontainer base image.
type: guide
---

# C / C++ / LLVM

The base image ships the standard Ubuntu C/C++ toolchain (`build-essential`,
`gcc`, `g++`, `binutils`, `gdb`, `cmake`, `ninja-build`, `pkg-config`) plus
the **latest available LLVM family** on Ubuntu 24.04 — currently LLVM 19.

LLVM is symlinked at `/opt/llvm` for stable paths:

* `LLVM_CONFIG=/opt/llvm/bin/llvm-config`
* `LIBRARY_PATH=/opt/llvm/lib`
* `BOLT_RT_INSTR_LIB=/opt/llvm/lib/libbolt_rt_instr.a`
* `PATH=/opt/llvm/bin:…`

`bolt-N`, `lld-N`, `llvm-N`, `llvm-N-dev` are all present. Mimalloc is
preinstalled (`libmimalloc-dev`) for projects that want a faster allocator.

The LLVM major version is passed as `LLVM_MAJOR` from the host CLI; the
Dockerfile contains no apt-cache probing.
