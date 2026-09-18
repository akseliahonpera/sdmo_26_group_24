FROM espressif/idf:latest

RUN apt-get update && \
    apt-get install -y git ninja-build libgcrypt20-dev libslirp-dev \
    libglib2.0-dev libpixman-1-dev libfdt-dev pkg-config && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone --depth 1 https://github.com/espressif/qemu.git qemu

WORKDIR /opt/qemu

RUN ./configure \
    --target-list=riscv32-softmmu \
    --enable-gcrypt \
    --enable-slirp

RUN ninja -C build

ENV PATH="/opt/qemu/build:$PATH"

WORKDIR /workspace
