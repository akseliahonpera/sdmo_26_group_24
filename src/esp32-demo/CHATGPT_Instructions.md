> [!NOTE]
> Promts used to generate these instructions and other content in ./firmware

Create a containerized esp32 simulator and a script that flashes wanted software to the simulated device

...

simplify more to an step by step process

...

The flash.bin doesnt exist. Error: root@c84652026ce6:/workspace# qemu-system-riscv32 \ -nographic \ -icount 3 \ -machine esp32c3 \ -drive file=firmware/build/flash.bin,if=mtd,format=raw qemu-system-riscv32: -drive file=firmware/build/flash.bin,if=mtd,format=raw: Could not open 'firmware/build/flash.bin': No such file or directory

...

Step 8. fails with 
Adding SPI flash device
qemu-system-riscv32: Drive size error: only 2, 4, 8, and 16MB images are supported
qemu-system-riscv32: -drive file=build/flash.bin,if=mtd,format=raw: machine type does not support if=mtd,bus=0,unit=0

update steps with a fix

...

manged to get it working on gemu. How to stop qemu run?

...

[main.c](./firmware/main/main.c)
Add a http get endpoint to this script . Note this is run on esp32.

also print host address in startup

...

Current version results in bootloop. This is run in emulation with qemu in espressif/idf docker container. Can this be setup so that the endpoint is accessible from the host machine

...

What if instead the esp should send a post request to another container instead

...

---
# ESP32-C3 Simulator — Step-by-Step

## Goal

Eventually you want:

```text
ESP32 simulator
      │
      │ temperature
      ▼
  API Gateway
      │
      ▼
    Server
```

We'll build it in small steps.

---

# Step 1 — Install Docker

Install Docker Desktop or Docker Engine.

Then check:

```bash
docker --version
```

You should get something like:

```text
Docker version 28.x
```

---

# Step 2 — Create a project

Create:

```text
esp32-demo/
```

Inside it:

```text
esp32-demo/
├── Dockerfile
├── docker-compose.yml
└── firmware/
```

Don't create anything else yet.

---

# Step 3 — Create the Docker container

Create `Dockerfile`:

```dockerfile
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
```

This gives you a container containing:

* ESP-IDF
* Espressif's QEMU
* tools needed to build ESP32-C3 firmware

---

# Step 4 — Create Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  esp32:
    build: .
    volumes:
      - ./firmware:/workspace/firmware
    working_dir: /workspace
    stdin_open: true
    tty: true
```

Build it:

```bash
docker compose build
```

This may take a while the first time.

---

# Step 5 — Check that the container works

Run:

```bash
docker compose run --rm esp32 bash
```

You should now be inside the container:

```text
root@...:/workspace#
```

Check ESP-IDF:

```bash

```

Check QEMU:

```bash
qemu-system-riscv32 --version
```

Check esptool:

```bash
esptool version
```

If all three commands work, stop here.

---

# Step 6 — Create a tiny ESP32 program

Inside `firmware/`, create:

```text
firmware/
├── CMakeLists.txt
└── main/
    ├── CMakeLists.txt
    └── main.c
```

### `firmware/CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(temperature_sensor)
```

### `firmware/main/CMakeLists.txt`

```cmake
idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
)
```

### `firmware/main/main.c`

Dummy sample current main contains network connection testing.
```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void)
{
    float temperature = 20.0;

    while (1) {
        printf("Temperature: %.1f C\n", temperature);

        temperature += 0.5;

        if (temperature > 30.0) {
            temperature = 20.0;
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

Output should looklike this. Eth is connected and trying to send requests.

```text
I (1013) main_task: Started on CPU0
I (1013) main_task: Calling app_main()
I (1013) qemu_device: Starting QEMU Ethernet device
I (1543) esp_eth.netif.netif_glue: 52:54:00:12:34:56
I (1543) esp_eth.netif.netif_glue: ethernet attached to netif
I (1643) qemu_device: Ethernet started
E (1643) esp_eth: esp_eth_ioctl(533): add mac address to filter not supported
E (1643) esp_eth.netif.netif_glue: eth_set_mac_filter(56): failed to add mac filter
E (1643) esp_netif_lwip: Failed to add multicast filter for IPv4
I (1643) qemu_device: Ethernet link up
I (1643) qemu_device: Ethernet initialization complete
I (1643) qemu_device: GET http://10.0.2.2:8080/health
E (1643) esp-tls: [sock=54] connect() error: Host is unreachable
E (1643) transport_base: Failed to open a new connection: 32772
E (1643) HTTP_CLIENT: Connection failed, sock < 0
E (1643) qemu_device: HTTP request failed: ESP_ERR_HTTP_CONNECT
I (1643) main_task: Returned from app_main()
I (2643) qemu_device: Got IP: 10.0.2.15
I (2643) qemu_device: Gateway: 10.0.2.2
I (2643) qemu_device: Netmask: 255.255.255.0
I (2643) esp_netif_handlers: eth ip: 10.0.2.15, mask: 255.255.255.0, gw: 10.0.2.
...
```

---

# Step 7 — Build the firmware

Enter the container:

```bash
docker compose run --rm esp32 bash
```

Then:

```bash
cd firmware
```

Set the target:

```bash
idf.py set-target esp32
```

Build:

```bash
idf.py build
```

If successful, you should have:

```text
firmware/
└── build/
    ├── bootloader/
    │   └── bootloader.bin
    ├── partition_table/
    │   └── partition-table.bin
    ├── temperature_sensor.bin
    ├── flash_args
    └── ...
```

At this point the ESP32-C3 firmware has been compiled.

---

# Step 8 — Create a QEMU-compatible flash image

**Do not manually run `esptool merge-bin` here.**

Use ESP-IDF's `merge-bin` command instead.

From:

```text
/workspace/firmware
```

run to create `flash.bin` first.

```bash

idf.py merge-bin -o flash.bin --fill-flash-size 4MB

```

This uses the flash arguments generated by ESP-IDF and pads the resulting image to exactly **4 MB**.

You should see output similar to:

```text
Wrote 0x400000 bytes to file build/flash.bin
```

The important part is:

```text
0x400000
```

because:

```text
0x400000 = 4 MB
```

Verify the file:

```bash
ls -lh build/flash.bin
```

You can also verify the exact size:

```bash
stat -c '%n %s bytes' build/flash.bin
```

Expected:

```text
build/flash.bin 4194304 bytes
```

You now have:

```text
/workspace/firmware/build/flash.bin
```

with a QEMU-supported 4 MB size.

Espressif's QEMU documentation specifies `--fill-flash-size 4MB` for this purpose and notes that QEMU supports 2, 4, 8, and 16 MB flash images.

---

# Step 9 — Run the ESP32-C3 in QEMU

You should still be in:

```text
/workspace/firmware
```

Run:

```bash
qemu-system-xtensa \
    -nographic \
    -icount 3 \
    -machine esp32 \
    -drive file=build/flash.bin,if=mtd,format=raw
```

Alternatively, from with network device:

```bash
qemu-system-xtensa \
    -nographic \
    -icount 3 \
    -machine esp32 \
    -drive file=build/flash.bin,if=mtd,format=raw \
    -nic user,model=open_eth,id=lo0
```

You should eventually see:

```text
Temperature: 20.0 C
Temperature: 20.5 C
Temperature: 21.0 C
Temperature: 21.5 C
```

If you see the temperature output, the ESP32-C3 firmware is running inside QEMU.

To stop execution `Ctrl + A, then X` in the terminal.

---

# Step 10 — If QEMU still reports a flash-size error

Before changing anything else, check:

```bash
stat -c '%s bytes' build/flash.bin
```

The expected result is:

```text
4194304 bytes
```

If you get a different number, recreate the image:

```bash
rm -f build/flash.bin

idf.py merge-bin \
    -o build/flash.bin \
    --fill-flash-size 4MB
```

Then verify again:

```bash
stat -c '%s bytes' build/flash.bin
```

It must report:

```text
4194304 bytes
```

Then retry QEMU.

---

# Step 11 — Only now add the API

Once QEMU successfully prints the temperature, don't immediately add ten more technologies.

Add one Python server:

```text
ESP32 simulator
       │
       │ HTTP
       ▼
 Python server
```

The ESP32 will eventually send:

```json
{
  "temperature": 24.5
}
```

to:

```text
POST /temperature
```

The Python server prints:

```text
Received temperature: 24.5 C
```

---

# Step 12 — Add the API gateway

Then change:

```text
ESP32
  │
  ▼
Python server
```

to:

```text
ESP32
  │
  ▼
API Gateway
  │
  ▼
Python server
```

At that point you've achieved the core of your industrial demo.

---

# The progression

Don't try to build everything at once:

```text
① Docker
   ↓
② ESP-IDF
   ↓
③ QEMU
   ↓
④ ESP32 firmware
   ↓
⑤ Build firmware
   ↓
⑥ Create 4 MB flash.bin
   ↓
⑦ Run ESP32-C3 in QEMU
   ↓
⑧ Simulated temperature
   ↓
⑨ HTTP
   ↓
⑩ API server
   ↓
⑪ API gateway
   ↓
⑫ Database
   ↓
⑬ Dashboard
```

The immediate milestone is now:

```text
idf.py build
      ↓
idf.py merge-bin --fill-flash-size 4MB
      ↓
build/flash.bin
      ↓
exactly 4 MB
      ↓
QEMU
      ↓
Temperature: 20.0 C
```

Once this works, the next step is small: make the virtual ESP32 send its temperature to a Python HTTP server.

