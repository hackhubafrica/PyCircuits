# Telemetry Protocol

Binary telemetry packet format for streaming plant state from ESP32 to host over serial/USB.

## Packet structure (C)

```c
// telemetry.h
#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdint.h>
#include <stddef.h>

typedef struct __attribute__((packed)) {
    uint8_t  sync1;     // Sync Byte 1: 0xAA
    uint8_t  sync2;     // Sync Byte 2: 0xBB
    uint32_t timestamp; // Time in microseconds (4 bytes)
    float    state_x;   // Modelica State Variable (4 bytes)
    float    input_u;   // Control Input Variable (4 bytes)
    uint8_t  checksum;  // Simple XOR checksum (1 byte)
} TelemetryPacket;

inline uint8_t calc_checksum(const uint8_t *data, size_t len) {
    uint8_t chk = 0;
    for (size_t i = 0; i < len; ++i) {
        chk ^= data[i];
    }
    return chk;
}

#endif
```

Packet size: **15 bytes** (2 sync + 4 timestamp + 4 state_x + 4 input_u + 1 checksum)

## C++ sender (ESP32)

```cpp
// main.cpp
#include <Arduino.h>
#include "telemetry.h"
#include "plant_model.h"

PlantState plant;
TelemetryPacket packet;

void send_telemetry() {
    packet.sync1 = 0xAA;
    packet.sync2 = 0xBB;
    packet.timestamp = micros();
    packet.state_x = plant.x;
    packet.input_u = plant.u;

    packet.checksum = calc_checksum(((uint8_t*)&packet) + 2, sizeof(TelemetryPacket) - 3);

    Serial.write((uint8_t*)&packet, sizeof(TelemetryPacket));
}
```

## Python receiver (pyserial + struct)

```python
import serial
import struct

PACKET_FORMAT = "<BBIffB"   # little-endian: 2B, I, 2f, B
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 15 bytes

def parse_stream(port="/dev/ttyUSB0", baudrate=115200):
    ser = serial.Serial(port, baudrate, timeout=1)

    while True:
        # Search for sync marker (0xAA 0xBB)
        if ser.read(1) == b'\xAA':
            if ser.read(1) == b'\xBB':
                payload = ser.read(PACKET_SIZE - 2)
                if len(payload) < PACKET_SIZE - 2:
                    continue

                full_buf = b'\xAA\xBB' + payload
                sync1, sync2, timestamp_us, state_x, input_u, checksum = \
                    struct.unpack(PACKET_FORMAT, full_buf)

                # Verify checksum
                computed_chk = 0
                for b in full_buf[2:-1]:
                    computed_chk ^= b

                if computed_chk == checksum:
                    time_sec = timestamp_us / 1e6
                    print(f"[{time_sec:.4f}s] State X: {state_x:.4f} | Input U: {input_u:.4f}")
                else:
                    print("Checksum error, frame dropped.")
```

## Go receiver (encoding/binary)

```go
package main

import (
    "bytes"
    "encoding/binary"
    "fmt"
    "log"

    "go.bug.st/serial"
)

type TelemetryPacket struct {
    Timestamp uint32
    StateX    float32
    InputU    float32
    Checksum  uint8
}

func main() {
    mode := &serial.Mode{BaudRate: 115200}
    port, err := serial.Open("/dev/ttyUSB0", mode)
    if err != nil {
        log.Fatalf("Failed to open serial port: %v", err)
    }
    defer port.Close()

    buf := make([]byte, 1)
    for {
        _, err := port.Read(buf)
        if err != nil || buf[0] != 0xAA {
            continue
        }
        _, err = port.Read(buf)
        if err != nil || buf[0] != 0xBB {
            continue
        }

        payload := make([]byte, 13)
        _, err = port.Read(payload)
        if err != nil {
            continue
        }

        var packet TelemetryPacket
        reader := bytes.NewReader(payload)
        err = binary.Read(reader, binary.LittleEndian, &packet)
        if err != nil {
            log.Println("Binary unpack error:", err)
            continue
        }

        fmt.Printf("[%d us] State X: %.4f | Input U: %.4f\n",
            packet.Timestamp, packet.StateX, packet.InputU)
    }
}
```

## Key benefits

| Benefit | Explanation |
|---------|-------------|
| Bandwidth savings | 15-byte binary packet takes ~3× less UART time than equivalent ASCII CSV (~35 bytes) |
| Zero MCU CPU overhead | Microcontroller writes directly from RAM to UART DMA registers; no `sprintf` or floating-point formatting |
| Deterministic layout | `__attribute__((packed))` ensures byte layout is deterministic across platforms |
| Checksum validation | XOR checksum catches corrupted frames |