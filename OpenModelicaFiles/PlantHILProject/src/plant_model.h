#pragma once
#include <stdint.h>

static constexpr uint8_t MODEL_STATE_COUNT = 1;
static constexpr float MODEL_A[MODEL_STATE_COUNT][MODEL_STATE_COUNT] = {
    {-20.0f}
};
static constexpr float MODEL_B[MODEL_STATE_COUNT] = {20.0f};
static constexpr float MODEL_C[MODEL_STATE_COUNT] = {1.0f};
static constexpr float MODEL_D = 0.0f;
