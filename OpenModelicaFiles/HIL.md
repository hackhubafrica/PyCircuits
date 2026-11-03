# Hardware-in-the-Loop (HIL) Deployment

ESP32 firmware deployment via PlatformIO for running compiled Modelica plants on hardware.

## PlatformIO project

Located at `PlantHILProject/`. Contains:

| Path | Purpose |
|------|---------|
| `platformio.ini` | PlatformIO project configuration |
| `src/` | Firmware source (compiled Modelica `Plant.h`/`Plant.c` synced here) |
| `include/` | Header files |
| `lib/` | Libraries |
| `test/` | Test files |

## Build and flash

```sh
cd OpenModelicaFiles/PlantHILProject
pio run              # Compile firmware
pio run -t upload    # Flash to ESP32
```

## ESP32 hardware limits for HIL simulation

| Resource | ESP32 Limit | Impact on Modelica plant models |
|----------|-------------|---------------------------------|
| Floating-Point Unit | Native 32-bit float; 64-bit double emulated in software | Compile OpenModelica targeting `float` to avoid severe CPU slowdowns |
| State dimension | 1–20 states at ≥1 kHz; >50 states taxes single core | Fine for DC-DC converters, motors, mechanical linkages; heavy power grids need faster MCU or FPGA |
| Nonlinear solvers / DAEs | Explicit ODEs run instantly; implicit DAEs with Newton-Raphson bottleneck real-time | Keep plant models in explicit state-space form; pre-solve algebraic loops during compilation |
| RAM & Flash | ~520 KB SRAM, 4–8 MB Flash | Generated C code ≈10–50 KB, leaving room for buffers |

## Mass-spring-damper on ESP32

A 2nd-order mass-spring-damper = 2 coupled first-order ODEs:

$$\dot{x}_1 = x_2$$
$$\dot{x}_2 = \frac{1}{m}(u - b x_2 - k x_1)$$

On an ESP32 at 240 MHz, updating these equations with Euler or RK4 takes <1 µs. Can clock at 10–50 kHz in a FreeRTOS hardware timer task, leaving >95% CPU free for telemetry streaming, PID, and communication.

## Real-time determinism

Standard OS (even Arch Linux with PREEMPT_RT) is non-deterministic. For HIL:

- **Microcontroller (FreeRTOS/bare-metal)**: hard real-time loops — PWM generation, fast PID, ADC reads
- **Host (Python/Julia/Rust)**: soft real-time — parameter tuning, logging, offline optimization, telemetry visualization

This boundary prevents OS context switches and scheduling jitter from destabilizing the control loop.