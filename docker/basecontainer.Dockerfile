# syntax=docker/dockerfile:1.7
#
# Logic-free base image for hostbootstrap.
#
# Every dynamic value (versions, download URLs, architecture strings, the CUDA
# base image) is an ARG resolved on the host by the hostbootstrap Python CLI
# and passed via `docker build --build-arg`. The Dockerfile only consumes ARGs;
# it does not branch on architecture, version, or flavor.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG IMAGE_FLAVOR
ARG TARGETARCH
ARG TOOL_ARCH
ARG NODE_ARCH
ARG GHCUP_ARCH
ARG AWS_ARCH
ARG PULUMI_ARCH
ARG LLVM_MAJOR
ARG GHC_VERSION
ARG CABAL_VERSION
ARG GO_VERSION
ARG GO_DOWNLOAD_URL
ARG NODE_VERSION
ARG NODE_DOWNLOAD_URL
ARG PURESCRIPT_VERSION
ARG PURESCRIPT_DOWNLOAD_URL
ARG KIND_VERSION
ARG KUBECTL_VERSION
ARG HELM_VERSION
ARG PULUMI_VERSION
ARG PULUMI_DOWNLOAD_URL
ARG KIND_DOWNLOAD_URL
ARG KUBECTL_DOWNLOAD_URL
ARG HELM_DOWNLOAD_URL
ARG MC_DOWNLOAD_URL
ARG AWS_DOWNLOAD_URL
ARG GHCUP_DOWNLOAD_URL
ARG RUST_TOOLCHAIN=stable

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        binutils \
        bolt-${LLVM_MAJOR} \
        ca-certificates \
        cmake \
        curl \
        dnsutils \
        docker-buildx \
        docker-compose-v2 \
        docker.io \
        file \
        g++ \
        gcc \
        gdb \
        git \
        gnupg \
        iproute2 \
        iptables \
        jq \
        less \
        libdnnl-dev \
        libffi-dev \
        libgmp-dev \
        libmimalloc-dev \
        libncurses-dev \
        libnuma-dev \
        libpq-dev \
        libssl-dev \
        libtinfo-dev \
        lld-${LLVM_MAJOR} \
        llvm-${LLVM_MAJOR} \
        llvm-${LLVM_MAJOR}-dev \
        make \
        ninja-build \
        openssh-client \
        perl \
        pkg-config \
        protobuf-compiler \
        python3 \
        python3-dev \
        python-is-python3 \
        python3-pip \
        python3-venv \
        skopeo \
        sudo \
        tini \
        unzip \
        wget \
        xz-utils \
        zlib1g-dev \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mkdir -p /workspace /opt/build /opt/cache /opt/cache/go /opt/cache/go/bin /opt/cache/go/build /opt/cache/go/mod; \
    ln -s "/usr/lib/llvm-${LLVM_MAJOR}" /opt/llvm

ENV BASECONTAINER_SOURCE_ROOT=/workspace \
    BASECONTAINER_BUILD_ROOT=/opt/build \
    BASECONTAINER_CACHE_ROOT=/opt/cache \
    CABAL_DIR=/opt/cache/cabal \
    PIP_CACHE_DIR=/opt/cache/python/pip \
    POETRY_CACHE_DIR=/opt/cache/python/pypoetry \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    PYTHONPYCACHEPREFIX=/opt/build/python/pycache \
    NPM_CONFIG_CACHE=/opt/cache/npm \
    NPM_CONFIG_PREFIX=/opt/build/node/global \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CARGO_HOME=/opt/cache/cargo \
    CARGO_TARGET_DIR=/opt/build/rust/target \
    GOROOT=/opt/go \
    GOPATH=/opt/cache/go \
    GOCACHE=/opt/cache/go/build \
    GOMODCACHE=/opt/cache/go/mod \
    GOTOOLCHAIN=local \
    LLVM_CONFIG=/opt/llvm/bin/llvm-config \
    LIBRARY_PATH=/opt/llvm/lib \
    BOLT_RT_INSTR_LIB=/opt/llvm/lib/libbolt_rt_instr.a \
    CC=gcc \
    CXX=g++ \
    RUSTUP_TOOLCHAIN=${RUST_TOOLCHAIN} \
    CARGO_HTTP_TIMEOUT=120 \
    CARGO_NET_RETRY=5 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

ENV PATH=/opt/llvm/bin:/opt/pulumi:/opt/go/bin:/opt/cache/go/bin:/root/.ghcup/bin:/opt/cache/cabal/bin:/root/.cabal/bin:/opt/cache/cargo/bin:/opt/build/node/global/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN set -eux; \
    tmpdir="$(mktemp -d)"; \
    curl -fsSL "${GO_DOWNLOAD_URL}" -o "${tmpdir}/go.tar.gz"; \
    rm -rf /opt/go; \
    tar -xzf "${tmpdir}/go.tar.gz" -C /opt; \
    rm -rf "${tmpdir}"; \
    /opt/go/bin/go version

RUN set -eux; \
    CGO_ENABLED=1 /opt/go/bin/go install github.com/NVIDIA/nvkind/cmd/nvkind@latest; \
    install -m 0755 /opt/cache/go/bin/nvkind /usr/local/bin/nvkind

RUN export PIP_BREAK_SYSTEM_PACKAGES=1 \
    && python -m pip install --ignore-installed --upgrade pip setuptools wheel poetry

RUN set -eux; \
    tmpdir="$(mktemp -d)"; \
    curl -fsSL "${NODE_DOWNLOAD_URL}" -o "${tmpdir}/node.tar.xz"; \
    tar -xJf "${tmpdir}/node.tar.xz" -C /usr/local --strip-components=1; \
    rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack; \
    printf '%s\n' \
      '#!/usr/bin/env bash' \
      'exec /usr/local/bin/node /usr/local/lib/node_modules/npm/bin/npm-cli.js "$@"' \
      > /usr/local/bin/npm; \
    chmod 0755 /usr/local/bin/npm; \
    rm -rf "${tmpdir}"

RUN set -eux; \
    tmpdir="$(mktemp -d)"; \
    curl -fsSL "${PURESCRIPT_DOWNLOAD_URL}" -o "${tmpdir}/purescript.tar.gz"; \
    tar -xzf "${tmpdir}/purescript.tar.gz" -C "${tmpdir}"; \
    install -m 0755 "${tmpdir}/purescript/purs" /usr/local/bin/purs; \
    rm -rf "${tmpdir}"

RUN npm install -g \
        @playwright/test \
        esbuild \
        playwright \
        purs-tidy \
        spago \
        typescript \
    && playwright install --with-deps chromium firefox webkit \
    && rm -rf /root/.npm

RUN set -eux; \
    curl -fsSL "${GHCUP_DOWNLOAD_URL}" -o /usr/local/bin/ghcup; \
    chmod 0755 /usr/local/bin/ghcup; \
    tmpdir="$(mktemp -d)"; \
    curl -fsSL "${KIND_DOWNLOAD_URL}" -o "${tmpdir}/kind"; \
    install -m 0755 "${tmpdir}/kind" /usr/local/bin/kind; \
    curl -fsSL "${KUBECTL_DOWNLOAD_URL}" -o "${tmpdir}/kubectl"; \
    install -m 0755 "${tmpdir}/kubectl" /usr/local/bin/kubectl; \
    curl -fsSL "${HELM_DOWNLOAD_URL}" -o "${tmpdir}/helm.tgz"; \
    tar -xzf "${tmpdir}/helm.tgz" -C "${tmpdir}"; \
    install -m 0755 "${tmpdir}/linux-${TOOL_ARCH}/helm" /usr/local/bin/helm; \
    curl -fsSL "${MC_DOWNLOAD_URL}" -o "${tmpdir}/mc"; \
    install -m 0755 "${tmpdir}/mc" /usr/local/bin/mc; \
    curl -fsSL "${AWS_DOWNLOAD_URL}" -o "${tmpdir}/awscliv2.zip"; \
    unzip -q "${tmpdir}/awscliv2.zip" -d "${tmpdir}"; \
    "${tmpdir}/aws/install" --install-dir /opt/aws-cli --bin-dir /usr/local/bin; \
    curl -fsSL "${PULUMI_DOWNLOAD_URL}" -o "${tmpdir}/pulumi.tgz"; \
    tar -xzf "${tmpdir}/pulumi.tgz" -C /opt; \
    test -x /opt/pulumi/pulumi; \
    rm -rf "${tmpdir}"

RUN ghcup install ghc "${GHC_VERSION}" \
    && ghcup set ghc "${GHC_VERSION}" \
    && ghcup install cabal "${CABAL_VERSION}" \
    && ghcup set cabal "${CABAL_VERSION}"

RUN cabal update \
    && cabal install \
        --jobs=1 \
        --ignore-project \
        --installdir /usr/local/bin \
        --install-method=copy \
        --overwrite-policy=always \
        fourmolu \
        hlint

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain "${RUSTUP_TOOLCHAIN}" \
    && rustup component add --toolchain "${RUSTUP_TOOLCHAIN}" llvm-tools-preview rustfmt

COPY support/haskell-deps/ /opt/basecontainer/haskell-deps/

RUN cd /opt/basecontainer/haskell-deps \
    && cabal update \
    && cabal build --jobs=1 all --only-dependencies \
    && cabal build --jobs=1 all

RUN set -eux; \
    if [ -d /usr/local/cuda/lib64 ]; then \
      printf '/usr/local/cuda/lib64\n' > /etc/ld.so.conf.d/cuda.conf; \
      ldconfig; \
    fi

WORKDIR /workspace
