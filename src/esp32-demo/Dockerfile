FROM espressif/idf:v6.1

RUN apt-get update && \
    apt-get install -y git ninja-build libgcrypt20-dev libslirp-dev \
    libglib2.0-dev libpixman-1-dev libfdt-dev pkg-config && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone --depth 1 https://github.com/espressif/qemu.git qemu

WORKDIR /opt/qemu

RUN ./configure --target-list=xtensa-softmmu \
    --enable-gcrypt \
    --enable-slirp \
    --enable-debug \
    --disable-strip \
    --disable-user \
    --disable-capstone \
    --disable-vnc \
    --disable-gtk

RUN ninja -C build

ENV PATH="/opt/qemu/build:$PATH"

WORKDIR /workspace
